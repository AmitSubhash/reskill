"""Quality rubric for LLM-generated questions.

Source: research pass citing Haladyna, Downing & Rodriguez 2002
(the 31-rule MCQ taxonomy), Rodriguez 2005 (three-option meta-analysis),
NBME item-writing guide, Arif et al. L@S 2024 on LLM-MCQ failure modes,
Anthropic prompt/jailbreak docs.

`validate_question(q, source_code)` returns a list of Flaw records.
Call `is_acceptable(flaws)` to decide whether to accept or retry.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass

from .question import Question


BANNED_STEM_PHRASES: tuple[str, ...] = (
    "which of the following is not",
    "which is not",
    "all of the following except",
    "which of these is never",
)
BANNED_OPTION_PHRASES: tuple[str, ...] = (
    "all of the above",
    "none of the above",
    "both a and",
    "a and c",
    "a and b",
)
ABSOLUTE_WORDS: tuple[str, ...] = ("always", "never", "impossible", "every time")
CUE_WORDS_IN_OPTION: tuple[str, ...] = ("may", "could", "might", "possibly")


@dataclass(frozen=True)
class Flaw:
    code: str
    severity: str  # "high" | "medium" | "low"
    detail: str


def validate_question(q: Question, source_code: str) -> list[Flaw]:
    """Score a generated Question against the research-backed rule set.

    Parameters
    ----------
    q : Question
        The parsed LLM output.
    source_code : str
        The snippet the question was generated from (used for the
        grounding check R8).

    Returns
    -------
    list[Flaw]
        Empty if every rule passed. Each Flaw has a rule code, severity,
        and detail string.
    """
    flaws: list[Flaw] = []
    stem = q.prompt.lower()
    options = [o.text.strip() for o in q.options]
    option_texts_lower = [t.lower() for t in options]
    correct_opts = [o for o in q.options if o.correct]

    # R4: one key, no convergence
    if len(correct_opts) != 1:
        flaws.append(
            Flaw("R4_multi_key", "high", f"{len(correct_opts)} correct options")
        )
    correct_text = correct_opts[0].text.strip() if correct_opts else ""
    correct_lower = correct_text.lower()

    # R5: banned formats
    for phrase in BANNED_STEM_PHRASES:
        if phrase in stem:
            flaws.append(
                Flaw("R5_negative_stem", "high", f"banned phrase in stem: {phrase!r}")
            )
    for i, opt in enumerate(option_texts_lower):
        for phrase in BANNED_OPTION_PHRASES:
            if phrase in opt:
                flaws.append(Flaw("R5_meta_option", "high", f"option {i}: {phrase!r}"))
        for word in ABSOLUTE_WORDS:
            if re.search(rf"\b{word}\b", opt):
                flaws.append(
                    Flaw("R5_absolute_term", "medium", f"option {i}: {word!r}")
                )
        for word in CUE_WORDS_IN_OPTION:
            if re.search(rf"\b{word}\b", opt):
                flaws.append(
                    Flaw("R5_cue_word", "low", f"option {i} hedges with {word!r}")
                )

    # Duplicate / near-duplicate options
    seen: set[str] = set()
    for i, opt in enumerate(option_texts_lower):
        normalized = re.sub(r"\s+", " ", opt).strip(".!?")
        if normalized in seen:
            flaws.append(
                Flaw("duplicate_option", "high", f"option {i} duplicates another")
            )
        seen.add(normalized)

    # R3: homogeneity -- length, longest-correct giveaway
    lengths = [len(o) for o in options]
    if lengths and max(lengths) > 2 * (sum(lengths) / len(lengths)):
        flaws.append(Flaw("R3_length_outlier", "medium", f"lengths {lengths}"))
    if (
        correct_opts
        and len(correct_text) == max(lengths)
        and max(lengths) > 1.4 * min(lengths)
    ):
        flaws.append(
            Flaw("R3_longest_is_correct", "high", "correct option is the longest")
        )

    # R9: explanation teaches, doesn't restate
    expl_lower = q.explanation.lower()
    key_words = [w for w in re.findall(r"[a-zA-Z_]{4,}", correct_lower)]
    if key_words and len(q.explanation) < 200:
        overlap = sum(1 for w in key_words if w in expl_lower) / len(key_words)
        if overlap > 0.7:
            flaws.append(
                Flaw("R9_explanation_restates", "medium", f"overlap={overlap:.2f}")
            )

    # R8: grounded in user_code
    identifiers = set(re.findall(r"\b[a-zA-Z_][a-zA-Z0-9_]{2,}\b", source_code))
    identifiers -= {
        "def", "class", "for", "from", "import", "return",
        "None", "True", "False", "self",
    }
    if identifiers and not any(tok in q.prompt for tok in identifiers):
        flaws.append(
            Flaw(
                "R8_ungrounded_stem",
                "high",
                "stem references no identifier from the snippet",
            )
        )

    # R1: cover-the-options -- stem must invite an answer
    meta_stems = (
        "which of these",
        "which of the following",
        "what is true",
        "which statement",
    )
    if len(q.prompt) < 60 and any(m in stem for m in meta_stems):
        flaws.append(
            Flaw("R1_meta_stem", "medium", "stem is generic; violates cover-the-options")
        )

    # R2: implausible-distractor heuristic -- throwaway error types
    stock_errors = (
        "importerror: no module",
        "typeerror: argument of type",
        "syntaxerror",
    )
    for i, opt in enumerate(option_texts_lower):
        if q.options[i].correct:
            continue
        if any(err in opt for err in stock_errors):
            err_type = next(e for e in stock_errors if e in opt)
            if err_type.split(":")[0] not in source_code.lower():
                flaws.append(
                    Flaw(
                        "R2_stock_distractor",
                        "medium",
                        f"option {i} throwaway error type",
                    )
                )

    # Convergence: distractors shouldn't all just permute the correct option
    corr_words = set(re.findall(r"[a-z_]{3,}", correct_lower))
    if corr_words:
        converging = 0
        for opt_lower in option_texts_lower:
            if opt_lower == correct_lower:
                continue
            opt_words = set(re.findall(r"[a-z_]{3,}", opt_lower))
            if not opt_words:
                continue
            shared = len(corr_words & opt_words) / len(corr_words)
            if shared > 0.6:
                converging += 1
        if converging >= len(options) - 1:
            flaws.append(
                Flaw("R4_convergence", "medium", "distractors converge on correct")
            )

    # Data-exfiltration heuristic: explanation leaking prompt tokens
    leak_tokens = ("system prompt", "these instructions", "role=", "you are now")
    for tok in leak_tokens:
        if tok in expl_lower:
            flaws.append(
                Flaw("exfil_suspect", "high", f"explanation mentions {tok!r}")
            )

    return flaws


def is_acceptable(flaws: Iterable[Flaw]) -> bool:
    """True when no HIGH-severity flaws are present."""
    return not any(f.severity == "high" for f in flaws)
