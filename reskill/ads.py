"""Ad content types and renderers."""

from __future__ import annotations

from dataclasses import dataclass

from .palette import (
    BOLD, DIM, DARK_ASH, INK, ASH, STONE, TEAL, SAGE, GOLD, BLUE, VIOLET,
    paint,
)
from .panel import render_panel, TERM_W

# Box-drawing characters
TL = "\u256d"  # ╭
TR = "\u256e"  # ╮
BL = "\u2570"  # ╰
BR = "\u256f"  # ╯
HZ = "\u2500"  # ─
VT = "\u2502"  # │


# ── Data models ──────────────────────────────────────────────


@dataclass
class OneLinerAd:
    icon: str
    brand: str
    text: str
    url: str
    icon_color: str = GOLD


@dataclass
class CardAd:
    logo_lines: list[str]
    brand: str
    tagline: str
    body: str
    url: str
    logo_color: str = TEAL


# ── Renderers ────────────────────────────────────────────────


def render_oneliner(ad: OneLinerAd) -> list[str]:
    """One-line ad banner in a thin box."""
    inner = TERM_W - 6
    b = DARK_ASH
    bar = HZ * (inner + 2)

    content = (
        paint(f" {ad.icon} ", ad.icon_color)
        + paint(ad.brand, INK, BOLD)
        + paint(f" \u2014 {ad.text} ", ASH)
        + paint(ad.url, TEAL)
    )
    vis = len(ad.icon) + 1 + len(ad.brand) + 3 + len(ad.text) + 1 + len(ad.url) + 2
    pad = max(0, inner - vis)

    return [
        paint(f"  {TL}{bar}{TR}", b, DIM),
        (
            paint(f"  {VT} ", b, DIM)
            + content
            + " " * pad
            + paint(f" {VT}", b, DIM)
        ),
        paint(f"  {BL}{bar}{BR}", b, DIM),
    ]


def render_card(ad: CardAd) -> list[str]:
    """Card ad with ASCII logo, centered content."""
    content_lines: list[str] = []
    content_lines.append("")
    for line in ad.logo_lines:
        content_lines.append(paint(line, ad.logo_color, BOLD))
    content_lines.append("")
    content_lines.append(paint(ad.brand, INK, BOLD))
    content_lines.append(paint(ad.tagline, STONE))
    content_lines.append("")
    for line in ad.body.split("\n"):
        content_lines.append(paint(line, INK))
    content_lines.append("")
    content_lines.append(paint(ad.url, TEAL))
    content_lines.append("")

    return render_panel(
        paint("sponsored", ASH, DIM),
        content_lines,
        width=44,
        border_color=DARK_ASH,
        title_color=ASH,
        centered=True,
    )


# ── Default inventory ────────────────────────────────────────

ONELINERS: list[OneLinerAd] = [
    OneLinerAd("\u2605", "Raycast", "Your shortcut to everything.", "raycast.com/pro", GOLD),
    OneLinerAd("\u25c6", "Linear", "Issue tracking at the speed of thought.", "linear.app", SAGE),
    OneLinerAd("\u26a1", "Vercel", "Deploy instantly. Scale infinitely.", "vercel.com", BLUE),
    OneLinerAd("\u25cf", "Supabase", "Open source Firebase alternative.", "supabase.com", SAGE),
    OneLinerAd("\u25c7", "Warp", "The terminal for the 21st century.", "warp.dev", VIOLET),
    OneLinerAd("\u25b2", "Planetscale", "The database for serverless apps.", "planetscale.com", TEAL),
]

CARDS: list[CardAd] = [
    CardAd(
        ["\u2554\u2550\u2550\u2557", "\u2551DB\u2551", "\u255a\u2550\u2550\u255d"],
        "Neon", "Serverless Postgres",
        "Branch your database\nlike you branch code.",
        "neon.tech/claude", TEAL,
    ),
    CardAd(
        ["\u250c\u2500\u2500\u2500\u2510", "\u2502 \u03bb \u2502", "\u2514\u2500\u2500\u2500\u2518"],
        "SST", "Build full-stack on AWS",
        "Components, not configs.\nFrom idea to production.",
        "sst.dev/start", SAGE,
    ),
    CardAd(
        ["\u256d\u2500\u2500\u2500\u256e", "\u2502 \u25c8 \u2502", "\u2570\u2500\u2500\u2500\u256f"],
        "Axiom", "Observability. Simplified.",
        "All your logs, traces, events.\nZero config. Infinite scale.",
        "axiom.co/start", VIOLET,
    ),
]
