"""Question scheduler -- chooses what to ask and when.

Current strategy (will be refined by the research pass):

  1. CONTEXT FILTER: look at live Claude transcript text and detect
     concepts that match. These are the "relevant now" pool.
  2. URGENCY RANK within the pool:
       a. overdue: concepts whose SM-2 `last + interval*86400 < now`
       b. new: concepts never answered
       c. not-due: everything else (avoided unless pool is empty)
  3. INTERLEAVE: never pick the same concept twice in a row if
     there's an alternative (interleaving > blocking for retention).
  4. FRESHNESS: never pick a question already in seen_questions
     unless all other options are exhausted.
  5. FALLBACKS (in order): git commit concepts -> cumulative cache
     -> global template bank.

SM-2 is per-concept (not per-question); rationale: questions in a
concept teach the same idea, so scheduling at concept granularity
gives room to show DIFFERENT questions of the same concept on
successive reviews (an implicit interleaving win).
"""

from __future__ import annotations

import random
import time
from dataclasses import dataclass

from . import state as state_mod
from .question import Question, TEMPLATE_BANK, detect_concepts


@dataclass(frozen=True)
class Pick:
    """A chosen question plus the reasoning the picker used.

    `source` values:
      - 'live'       -- matched the current Claude transcript
      - 'commit'     -- matched a recent git commit
      - 'due'        -- SM-2 said this concept is overdue
      - 'new'        -- concept never answered before
      - 'fallback'   -- nothing else matched; random pick
    """

    question: Question
    concept: str
    source: str


_SECONDS_PER_DAY = 86400


def _is_overdue(concept_state: dict, now: float) -> bool:
    last = concept_state.get("last", 0.0)
    interval_days = concept_state.get("interval", 1)
    return (now - last) >= interval_days * _SECONDS_PER_DAY


def _concept_label_for_key(key: str) -> str:
    """Map a detect_concepts() pattern key ('lru_cache') to the semantic
    concept label Question.concept uses ('caching').

    The mapping comes from the first question in the bank for that key.
    """
    bank = TEMPLATE_BANK.get(key, [])
    return bank[0].concept if bank else key


def _bucketize(
    pattern_keys: list[str],
    state: state_mod.State,
    now: float,
) -> tuple[list[str], list[str], list[str]]:
    """Split candidate pattern keys into (overdue, new, not_yet_due).

    We look up state via the SEMANTIC concept label (Question.concept,
    how record_answer keys its SM-2 dict), not the pattern key.
    """
    overdue: list[str] = []
    new: list[str] = []
    not_due: list[str] = []
    for key in pattern_keys:
        label = _concept_label_for_key(key)
        cs = state.concepts.get(label)
        if cs is None or cs.get("total", 0) == 0:
            new.append(key)
        elif _is_overdue(cs, now):
            overdue.append(key)
        else:
            not_due.append(key)
    return overdue, new, not_due


def _fresh_questions(concept: str, seen_ids: set[str]) -> list[Question]:
    bank = TEMPLATE_BANK.get(concept, [])
    return [q for q in bank if q.id not in seen_ids]


def _pick_from_concepts(
    pattern_keys: list[str],
    seen_ids: set[str],
    avoid_concept: str | None = None,
) -> tuple[Question, str] | None:
    """Pick a fresh question from these bank pattern keys.

    Shuffles for variety. Avoids questions whose SEMANTIC concept label
    matches `avoid_concept` -- used for interleaving so the same concept
    isn't asked twice in a row.
    """
    shuffled = list(pattern_keys)
    random.shuffle(shuffled)
    preferred: list[str] = []
    deprioritized: list[str] = []
    for key in shuffled:
        if avoid_concept and _concept_label_for_key(key) == avoid_concept:
            deprioritized.append(key)
        else:
            preferred.append(key)
    for key in preferred + deprioritized:
        fresh = _fresh_questions(key, seen_ids)
        if fresh:
            q = random.choice(fresh)
            return q, q.concept
    return None


def choose(
    live_text: str,
    commit_text: str,
    state: state_mod.State,
    seen_ids: set[str],
    last_concept: str | None = None,
) -> Pick | None:
    """Return the next question to show, or None if nothing fits.

    Parameters
    ----------
    live_text : str
        Recent Claude transcript content.
    commit_text : str
        Concatenated recent commit diffs (optional context).
    state : state_mod.State
        User state with SM-2 per-concept data.
    seen_ids : set[str]
        Question IDs the user has already answered; we avoid these.
    last_concept : str or None
        The concept of the most recently-asked question; used to
        interleave (Rohrer & Taylor 2007: interleaved practice
        outperforms blocked for retention).
    """
    now = time.time()

    live_concepts = list(dict.fromkeys(detect_concepts(live_text))) if live_text else []
    commit_concepts = list(dict.fromkeys(detect_concepts(commit_text))) if commit_text else []

    # Tier 1: live context, SM-2-prioritized
    if live_concepts:
        overdue, new, not_due = _bucketize(live_concepts, state, now)
        for bucket, source in ((overdue, "due"), (new, "new"), (not_due, "live")):
            picked = _pick_from_concepts(bucket, seen_ids, avoid_concept=last_concept)
            if picked:
                q, concept = picked
                return Pick(question=q, concept=concept, source=source)

    # Tier 2: commit context
    if commit_concepts:
        overdue, new, not_due = _bucketize(commit_concepts, state, now)
        for bucket, source in ((overdue, "due"), (new, "new"), (not_due, "commit")):
            picked = _pick_from_concepts(bucket, seen_ids, avoid_concept=last_concept)
            if picked:
                q, concept = picked
                return Pick(question=q, concept=concept, source=source)

    # Tier 3: whole bank, still SM-2 aware
    all_concepts = list(TEMPLATE_BANK.keys())
    overdue, new, _ = _bucketize(all_concepts, state, now)
    for bucket, source in ((overdue, "due"), (new, "new")):
        picked = _pick_from_concepts(bucket, seen_ids, avoid_concept=last_concept)
        if picked:
            q, concept = picked
            return Pick(question=q, concept=concept, source=source)

    # Tier 4: last resort -- accept a previously-seen question.
    # This usually means the user has exhausted the bank.
    for concept in random.sample(all_concepts, k=len(all_concepts)):
        bank = TEMPLATE_BANK.get(concept, [])
        if bank:
            return Pick(
                question=random.choice(bank),
                concept=concept,
                source="fallback",
            )

    return None


def concepts_ready(
    live_text: str,
    state: state_mod.State,
    seen_ids: set[str],
) -> tuple[int, int]:
    """Quick count of (due, new) concepts relevant to the current context.

    Used by the idle card to surface "3 due, 12 new" so the user has a
    sense of what's in the queue.
    """
    now = time.time()
    concepts = list(dict.fromkeys(detect_concepts(live_text))) if live_text else list(TEMPLATE_BANK.keys())
    overdue, new, _ = _bucketize(concepts, state, now)
    # Only count as "available" if there's at least one fresh question.
    due_n = sum(1 for c in overdue if _fresh_questions(c, seen_ids))
    new_n = sum(1 for c in new if _fresh_questions(c, seen_ids))
    return due_n, new_n
