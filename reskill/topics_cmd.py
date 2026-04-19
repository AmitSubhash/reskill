"""`reskill topics` -- see every concept + your mastery progress.

Essentially a "learning map": which concepts you've been seen,
which you've mastered, which you've never touched. Useful for
users who want to know what's in the bank and where the gaps are.
"""

from __future__ import annotations

from collections import defaultdict

from . import state as state_mod
from .palette import ASH, BOLD, DIM, GOLD, ROSE, SAGE, STONE, TEAL, paint
from .question import PATTERNS, TEMPLATE_BANK


def _concept_of_bank_key(key: str) -> str:
    """Pattern key -> semantic concept label (Question.concept)."""
    bank = TEMPLATE_BANK.get(key, [])
    return bank[0].concept if bank else key


def _cluster_of(key: str) -> str:
    """Return the cluster name for a concept key, or 'other'."""
    from .scheduler import CONFUSABLE_CLUSTERS
    for cluster, members in CONFUSABLE_CLUSTERS.items():
        if key in members:
            return cluster
    return "other"


def run() -> int:
    state = state_mod.load()
    print()
    print(paint("  reSkill", TEAL, BOLD) + paint("  topics", ASH))
    print()

    by_cluster: dict[str, list[tuple[str, str]]] = defaultdict(list)
    for key, label, _ in PATTERNS:
        if key in TEMPLATE_BANK:
            by_cluster[_cluster_of(key)].append((key, label))

    total_mastered = 0
    total_touched = 0
    total_concepts = sum(len(v) for v in by_cluster.values())

    for cluster, concepts in sorted(by_cluster.items()):
        display = cluster.replace("-", " ") if cluster != "other" else "other"
        print("  " + paint(display, TEAL, BOLD))
        for key, label in concepts:
            semantic = _concept_of_bank_key(key)
            cs = state.concepts.get(semantic, {})
            total = cs.get("total", 0)
            correct = cs.get("correct", 0)
            bank_size = len(TEMPLATE_BANK.get(key, []))
            rate = correct / total if total else 0.0

            if total == 0:
                glyph = paint("\u25cb", STONE)      # hollow circle -- new
                status_color = STONE
                status = "new"
            elif rate >= 0.8 and total >= 2:
                glyph = paint("\u25cf", SAGE, BOLD)   # solid -- mastered
                status_color = SAGE
                status = f"{int(rate*100)}%"
                total_mastered += 1
            elif rate >= 0.5:
                glyph = paint("\u25d0", GOLD)        # half -- partial
                status_color = GOLD
                status = f"{int(rate*100)}%"
                total_touched += 1
            else:
                glyph = paint("\u25cf", ROSE)       # solid red -- struggling
                status_color = ROSE
                status = f"{int(rate*100)}%"
                total_touched += 1

            if total == 0:
                activity = f"{bank_size} question{'s' if bank_size != 1 else ''} available"
            else:
                activity = f"{correct}/{total} correct"
            line = (
                "    "
                + glyph
                + "  "
                + paint(label.ljust(26), BOLD)
                + paint(status.rjust(5), status_color)
                + paint(f"   {activity}", ASH, DIM)
            )
            print(line)
        print()

    summary = (
        paint(f"  {total_mastered} mastered", SAGE, BOLD)
        + paint(f"   {total_touched} in progress", GOLD)
        + paint(
            f"   {total_concepts - total_mastered - total_touched} new",
            ASH, DIM,
        )
        + paint(f"   of {total_concepts}", ASH, DIM)
    )
    print(summary)
    print()

    if total_mastered == 0:
        print(paint("  try `reskill next` to get started", ASH, DIM))
    elif total_mastered < total_concepts // 3:
        print(paint("  try `reskill session --since 14d` to widen coverage", ASH, DIM))
    else:
        print(paint("  try `reskill review` to shore up the tricky ones", ASH, DIM))
    print()

    return 0
