"""
All 10 ad rendering patterns for terminal, demoed sequentially.
Run: python -m reskill.patterns
"""

from __future__ import annotations

import itertools
import os
import shutil
import sys
import time

from .palette import (
    BOLD, DIM, RESET,
    INK, STONE, ASH, DARK_ASH, SAGE, TEAL, ROSE, VIOLET, GOLD, BLUE,
    rgb, bg_rgb, paint,
)
from .panel import render_panel, visible_len, TL, TR, BL, BR, HZ, VT, LT, RT

TERM_W = min(shutil.get_terminal_size().columns, 90)


def hr() -> None:
    print(paint(f"  {HZ * (TERM_W - 4)}", DARK_ASH, DIM))


def section(num: int, title: str, desc: str) -> None:
    print()
    hr()
    print(f"  {paint(f'Pattern {num}', TEAL, BOLD)}  {paint(title, INK, BOLD)}")
    print(f"  {paint(desc, ASH)}")
    hr()
    print()


def pause(seconds: float = 2.0) -> None:
    time.sleep(seconds)


# ── Pattern 1: Statusline ────────────────────────────────────


def pattern_1_statusline() -> None:
    section(1, "Statusline Injection",
            "Persistent bottom bar. Lowest disruption. Always visible.")

    # Simulate a statusline
    bar_bg = bg_rgb(45, 53, 59)
    content = (
        f"{bar_bg} "
        + paint(" amit@mac ", rgb(167, 192, 128), BOLD) + bar_bg
        + paint(" ~/Projects/reskill ", rgb(127, 187, 179)) + bar_bg
        + paint(" (main) ", rgb(157, 169, 160)) + bar_bg
        + paint(" Opus 4.6 ", rgb(214, 153, 182)) + bar_bg
        + paint(" ctx:42% ", rgb(133, 146, 137)) + bar_bg
        + "  "
        + paint("Sponsored by ", rgb(92, 106, 114)) + bar_bg
        + paint("Raycast ", rgb(219, 188, 127), BOLD) + bar_bg
        + paint(chr(0x2605), rgb(219, 188, 127)) + bar_bg
        + " " * 10
        + RESET
    )
    print(content)
    print()
    print(f"  {paint('^ Brand sits in the statusline, always visible, zero disruption', ASH)}")
    pause()


# ── Pattern 2: Spinner Tip ───────────────────────────────────


def pattern_2_spinner_tip() -> None:
    section(2, "Spinner Tip Replacement",
            "Text next to thinking spinner. Transient.")

    spinner = itertools.cycle("\u280b\u2819\u2839\u2838\u283c\u2834\u2826\u2827\u2807\u280f")
    tips = [
        "Sponsored by Raycast -- raycast.com/pro",
        "Try Linear: issue tracking at the speed of thought",
        "Vercel -- deploy instantly, scale infinitely",
    ]
    for tip_idx in range(3):
        for i in range(15):
            s = next(spinner)
            verb = ["Cogitating", "Ruminating", "Deliberating"][tip_idx]
            tip = tips[tip_idx]
            sys.stdout.write(
                f"\r  {paint(s, TEAL)} {paint(f'{verb}...', ASH)}"
                f"  {paint(tip, DARK_ASH, DIM)}"
                f"{' ' * 10}"
            )
            sys.stdout.flush()
            time.sleep(0.08)
    sys.stdout.write("\r" + " " * (TERM_W) + "\r")
    print(f"  {paint('^ Tip rotates during thinking, vanishes on response', ASH)}")
    pause()


# ── Pattern 3: Boxen Banner ─────────────────────────────────


def pattern_3_boxen() -> None:
    section(3, "Boxen Banner (npm update-notifier style)",
            "THE established CLI notification pattern. After output, in scrollback.")

    inner = 50
    bar = HZ * (inner + 2)
    b = GOLD

    lines = [
        paint(f"  {TL}{bar}{TR}", b),
        paint(f"  {VT}", b) + " " * (inner + 2) + paint(VT, b),
        (
            paint(f"  {VT}", b) + "  "
            + paint(chr(0x2605) + " ", GOLD)
            + paint("Raycast", INK, BOLD)
            + paint(" -- Your shortcut to everything", ASH)
            + " " * 4
            + paint(VT, b)
        ),
        (
            paint(f"  {VT}", b) + "  "
            + paint("Try it free: ", STONE)
            + paint("raycast.com/pro", TEAL)
            + " " * 15
            + paint(VT, b)
        ),
        paint(f"  {VT}", b) + " " * (inner + 2) + paint(VT, b),
        paint(f"  {BL}{bar}{BR}", b),
    ]
    for line in lines:
        print(line)
    print()
    print(f"  {paint('^ Yellow rounded border, centered text, padding. The classic.', ASH)}")
    pause()


# ── Pattern 4: Left Accent Bar ───────────────────────────────


def pattern_4_accent_bar() -> None:
    section(4, "Left Accent Bar (opencode/Feynman style)",
            "Blends into chat flow like a native message.")

    accent = rgb(219, 188, 127)  # gold
    bar_char = "\u2503"  # ┃ thick vertical

    lines = [
        f"  {paint(bar_char, accent)}  {paint(chr(0x2605) + ' Raycast', INK, BOLD)}",
        f"  {paint(bar_char, accent)}  {paint('Your shortcut to everything.', STONE)}",
        f"  {paint(bar_char, accent)}  {paint('raycast.com/pro', TEAL)}",
    ]
    print()
    for line in lines:
        print(line)
    print()
    print(f"  {paint('^ Looks like another message in the conversation', ASH)}")
    pause()


# ── Pattern 5: Static Zone ──────────────────────────────────


def pattern_5_static() -> None:
    section(5, "Static Zone Injection (Ink <Static>)",
            "Renders once at session start. Permanent in scrollback, never re-renders.")

    # Simulate session start banner
    inner = TERM_W - 8
    bar = HZ * (inner + 2)
    b = DARK_ASH

    print(paint(f"    {TL}{bar}{TR}", b, DIM))
    content = (
        paint(f"    {VT} ", b, DIM)
        + paint("This session is sponsored by ", ASH)
        + paint("Neon", TEAL, BOLD)
        + paint(" -- Serverless Postgres. ", ASH)
        + paint("neon.tech/claude", TEAL)
    )
    pad = inner - visible_len("This session is sponsored by Neon -- Serverless Postgres. neon.tech/claude")
    print(content + " " * max(0, pad) + paint(f" {VT}", b, DIM))
    print(paint(f"    {BL}{bar}{BR}", b, DIM))
    print()
    print(f"  {paint('^ One-shot banner. Like a session MOTD. Zero flicker.', ASH)}")
    pause()


# ── Pattern 6: Floating Overlay with Shadow ──────────────────


def pattern_6_overlay() -> None:
    section(6, "Floating Overlay with Shadow",
            "opencode-style string compositing. Centers on screen.")

    # Build background (fake terminal content)
    bg_lines = []
    for i in range(8):
        if i == 0:
            bg_lines.append(paint(f"  {chr(0x276f)} fix the login bug in auth.py", INK, DIM))
        elif i == 1:
            bg_lines.append(paint(f"  {chr(0x2699)} Read src/auth.py", GOLD, DIM))
        elif i == 2:
            bg_lines.append(paint("  I'll fix the session handling...", INK, DIM))
        else:
            bg_lines.append(paint("  " + "." * 40, DARK_ASH, DIM))

    # Build overlay
    shadow_char = "\u2591"  # ░
    shadow_color = rgb(40, 40, 40)
    ov_w = 44
    ov_inner = ov_w - 4

    ov_lines = []
    ov_bar = HZ * (ov_inner + 2)
    ov_lines.append(paint(f"{TL}{ov_bar}{TR}", DARK_ASH, BOLD))
    ov_lines.append(
        paint(f"{VT} ", DARK_ASH, BOLD)
        + paint("sponsored", ASH, DIM)
        + " " * (ov_inner - 9)
        + paint(f" {VT}", DARK_ASH, BOLD)
    )
    ov_lines.append(paint(f"{LT}{ov_bar}{RT}", DARK_ASH, DIM))

    card_content = [
        "",
        paint("\u2554\u2550\u2550\u2557", TEAL, BOLD),
        paint("\u2551DB\u2551", TEAL, BOLD),
        paint("\u255a\u2550\u2550\u255d", TEAL, BOLD),
        "",
        paint("Neon", INK, BOLD),
        paint("Serverless Postgres", STONE),
        "",
        paint("Branch your database", INK),
        paint("like you branch code.", INK),
        "",
        paint("neon.tech/claude", TEAL),
        "",
    ]
    for cl in card_content:
        vl = visible_len(cl)
        pad_l = max(0, (ov_inner - vl) // 2)
        pad_r = max(0, ov_inner - vl - pad_l)
        ov_lines.append(
            paint(f"{VT} ", DARK_ASH, BOLD)
            + " " * pad_l + cl + " " * pad_r
            + paint(f" {VT}", DARK_ASH, BOLD)
        )
    ov_lines.append(paint(f"{BL}{ov_bar}{BR}", DARK_ASH, BOLD))

    # Composite: center overlay on bg, add shadow
    offset_x = (TERM_W - ov_w) // 2
    for i, bg_line in enumerate(bg_lines):
        ov_idx = i - 0  # start overlay at row 0
        if 0 <= ov_idx < len(ov_lines):
            # Print bg prefix, then overlay, then shadow
            print(" " * offset_x + ov_lines[ov_idx] + paint(shadow_char, shadow_color))
        elif ov_idx == len(ov_lines):
            # Shadow bottom
            print(" " * (offset_x + 1) + paint(shadow_char * (ov_w), shadow_color))
        else:
            print(bg_line)

    # Print remaining overlay lines
    for ov_idx in range(len(bg_lines), len(ov_lines)):
        print(" " * offset_x + ov_lines[ov_idx] + paint(shadow_char, shadow_color))
    print(" " * (offset_x + 1) + paint(shadow_char * (ov_w), shadow_color))

    print()
    print(f"  {paint('^ Floats over content with shadow. Disappears when thinking ends.', ASH)}")
    pause()


# ── Pattern 7: Half-block Image Card ─────────────────────────


def pattern_7_halfblock() -> None:
    section(7, "Half-Block Image Card",
            "Full-color logo via unicode half-blocks. Works in all truecolor terms.")

    # Render a simple "R" logo using half-blocks
    half = "\u2584"  # ▄
    # 6x6 pixel grid for a stylized "R" (each row = 2 pixel rows via half-block)
    # Using gold (#dbbc7f) on dark bg (#2d353b)
    fg = rgb(219, 188, 127)
    bg = bg_rgb(45, 53, 59)
    fg2 = rgb(127, 187, 179)  # teal accent

    logo_lines = [
        f"{bg}{fg}\u2588\u2588\u2588\u2588\u2584{RESET}  ",
        f"{bg}{fg}\u2588{RESET}{bg}  {fg}\u2588{RESET}{bg} {RESET} ",
        f"{bg}{fg}\u2588\u2588\u2588\u2588\u2580{RESET}  ",
        f"{bg}{fg}\u2588{RESET}{bg} {fg}\u2588{RESET}{bg}  {RESET} ",
        f"{bg}{fg}\u2588{RESET}{bg}  {fg2}\u2588{RESET}{bg} {RESET} ",
    ]

    panel_lines = render_panel(
        paint("sponsored", ASH, DIM),
        [
            "",
            *logo_lines,
            "",
            paint("ReSkill", INK, BOLD),
            paint("Terminal ads for AI agents", STONE),
            "",
            paint("reskill.dev", TEAL),
            "",
        ],
        width=38,
        border_color=DARK_ASH,
        title_color=ASH,
        centered=True,
    )
    for line in panel_lines:
        print(line)
    print()
    print(f"  {paint('^ Logo rendered with half-block chars. No image protocol needed.', ASH)}")
    pause()


# ── Pattern 8: Gradient Big Text ─────────────────────────────


def pattern_8_bigtext() -> None:
    section(8, "Gradient ASCII Big Text",
            "figlet/cfonts style banner with color gradient. Attention-grabbing.")

    # Hand-coded small ASCII art with gradient
    colors = [
        rgb(230, 126, 128),  # rose
        rgb(219, 188, 127),  # gold
        rgb(167, 192, 128),  # sage
        rgb(127, 187, 179),  # teal
        rgb(214, 153, 182),  # violet
    ]

    banner = [
        " ██████  ███████ ███████ ██   ██ ██ ██      ██     ",
        " ██   ██ ██      ██      ██  ██  ██ ██      ██     ",
        " ██████  █████   ███████ █████   ██ ██      ██     ",
        " ██   ██ ██           ██ ██  ██  ██ ██      ██     ",
        " ██   ██ ███████ ███████ ██   ██ ██ ███████ ███████",
    ]

    for i, line in enumerate(banner):
        c = colors[i % len(colors)]
        print(f"  {paint(line, c, BOLD)}")

    print()
    print(f"  {paint('Terminal ads for AI coding agents', STONE)}")
    print(f"  {paint('reskill.dev', TEAL)}")
    print()
    print(f"  {paint('^ Big ASCII banner with per-line gradient. Maximum brand impact.', ASH)}")
    pause()


# ── Pattern 9: Toast / Auto-dismiss ─────────────────────────


def pattern_9_toast() -> None:
    section(9, "Toast Notification (lazygit/k9s style)",
            "Bottom-anchored, auto-dismisses after timeout.")

    # Show a toast that fades
    toast_bg = bg_rgb(55, 66, 71)
    for tick in range(20):
        if tick < 15:
            msg = (
                f"\r  {toast_bg} "
                + paint(chr(0x2605) + " ", GOLD)
                + paint("Raycast", INK, BOLD)
                + toast_bg
                + paint(" -- Try it free at ", ASH)
                + paint("raycast.com/pro ", TEAL)
                + toast_bg + " " + RESET
            )
        else:
            # Fade out
            dim_level = (tick - 14) * 30
            c = rgb(92 + dim_level, 106 + dim_level, 114 + dim_level)
            msg = f"\r  {paint('  ...  ', c, DIM)}{' ' * 60}"
        sys.stdout.write(msg)
        sys.stdout.flush()
        time.sleep(0.15)

    sys.stdout.write("\r" + " " * TERM_W + "\r")
    print(f"  {paint('^ Appears at bottom, auto-fades after 2-3s. Non-blocking.', ASH)}")
    pause()


# ── Pattern 10: Native Image (concept only) ──────────────────


def pattern_10_native_image() -> None:
    section(10, "Native Image Protocol (concept)",
            "True photographic rendering. iTerm2/Kitty/WezTerm only.")

    print(f"  {paint('This requires a supported terminal + actual image data.', STONE)}")
    print(f"  {paint('Use ink-picture for Ink apps or terminal-image for Node.js.', STONE)}")
    print()
    print(f"  {paint('Fallback chain:', INK)}")
    print(f"  {paint('  Kitty protocol', TEAL)} {paint('(best quality, Kitty/Ghostty/WezTerm)', ASH)}")
    print(f"  {paint('  > iTerm2 protocol', TEAL)} {paint('(iTerm2, VS Code, mintty)', ASH)}")
    print(f"  {paint('  > Sixel', TEAL)} {paint('(WezTerm, foot, mlterm, Windows Terminal)', ASH)}")
    print(f"  {paint('  > Half-block', SAGE)} {paint('(any truecolor terminal) <-- Pattern 7', ASH)}")
    print(f"  {paint('  > Braille', STONE)} {paint('(monochrome, highest spatial resolution)', ASH)}")
    print(f"  {paint('  > ASCII', DARK_ASH)} {paint('(universal fallback)', ASH)}")
    print()
    print(f"  {paint('ink-picture auto-detects and picks the best available.', ASH)}")
    pause(1.0)


# ── Main ─────────────────────────────────────────────────────


def run() -> None:
    os.system("clear")
    print()
    print(f"  {paint('reSkill', TEAL, BOLD)} {paint('Pattern Catalog', INK)}")
    print(f"  {paint('10 ways to render ad content in a terminal', ASH)}")
    print()
    pause(1.0)

    pattern_1_statusline()
    pattern_2_spinner_tip()
    pattern_3_boxen()
    pattern_4_accent_bar()
    pattern_5_static()
    pattern_6_overlay()
    pattern_7_halfblock()
    pattern_8_bigtext()
    pattern_9_toast()
    pattern_10_native_image()

    print()
    hr()
    print(f"  {paint('All 10 patterns demonstrated.', TEAL, BOLD)}")
    print(f"  {paint('Pick your favorites and we build them for real.', ASH)}")
    hr()
    print()


if __name__ == "__main__":
    run()
