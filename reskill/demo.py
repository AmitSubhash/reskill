"""Full Claude Code session simulation with ad boxes."""

from __future__ import annotations

import os
import time

from .palette import (
    BOLD, DIM, DARK_ASH, INK, ASH, STONE, TEAL, SAGE, GOLD,
    paint,
)
from .panel import render_panel, TERM_W
from .spinner import show_thinking
from .ads import ONELINERS, CARDS


# ── Helpers ──────────────────────────────────────────────────


def user_prompt(text: str) -> None:
    print()
    print(f"  {paint(chr(0x276f), SAGE, BOLD)} {paint(text, INK, BOLD)}")


def tool_call(name: str, arg: str = "") -> None:
    print(f"  {paint(chr(0x2699), GOLD)} {paint(name, GOLD, BOLD)} {paint(arg, ASH)}")


def success(text: str) -> None:
    print(f"  {paint(chr(0x2713), SAGE, BOLD)} {paint(text, ASH)}")


def assistant_text(text: str) -> None:
    print()
    for line in text.split("\n"):
        print(f"  {paint(line, INK)}")


def code_block(code: str, lang: str = "python") -> None:
    lines: list[str] = []
    for i, line in enumerate(code.strip().split("\n"), 1):
        num = paint(f"{i:>3} ", DARK_ASH)
        lines.append(num + paint(line, INK))

    panel_lines = render_panel(
        paint(f"  {lang}", STONE),
        lines,
        border_color=STONE,
        title_color=STONE,
    )
    print()
    for line in panel_lines:
        print(line)


def test_output(passed: int, failed: int = 0, duration: float = 0.34) -> None:
    lines: list[str] = []
    for i in range(passed):
        lines.append(
            paint(f"  tests/test_api.py::test_{i + 1} ", INK)
            + paint("PASSED", SAGE, BOLD)
        )
    lines.append("")
    summary = paint(f"  {passed} passed", SAGE, BOLD)
    if failed:
        summary += paint(f", {failed} failed", STONE, BOLD)
    summary += paint(f" in {duration}s", ASH)
    lines.append(summary)

    border = SAGE if not failed else STONE
    panel_lines = render_panel(
        paint("  output", STONE),
        lines,
        border_color=border,
        title_color=border,
    )
    print()
    for line in panel_lines:
        print(line)


# ── Main session ─────────────────────────────────────────────


def run() -> None:
    os.system("clear")

    # Header
    print()
    hr = chr(0x2500) * (TERM_W - 4)
    print(f"  {paint('claude code', TEAL, BOLD)}  {paint('v2.1.88', DARK_ASH)}")
    print(paint(f"  {hr}", DARK_ASH, DIM))
    print()
    time.sleep(0.8)

    # ── Turn 1 ───────────────────────────────────────────────
    user_prompt("add a /health endpoint to the FastAPI app")
    time.sleep(0.4)

    show_thinking(3.0, ad=ONELINERS[0])

    tool_call("Read", "src/main.py")
    time.sleep(0.3)
    assistant_text("I'll add a health check endpoint to your FastAPI app.")

    code_block('''@app.get("/health")
async def health_check() -> dict[str, str]:
    """Health check endpoint for load balancer."""
    return {"status": "ok", "version": app.version}''')

    tool_call("Edit", "src/main.py")
    time.sleep(0.2)
    success("Applied edit to src/main.py")
    time.sleep(1.5)

    # ── Turn 2 ───────────────────────────────────────────────
    user_prompt("write tests for it")
    time.sleep(0.4)

    show_thinking(4.5, ad=CARDS[0])

    tool_call("Read", "tests/test_api.py")
    time.sleep(0.2)
    assistant_text("Added tests for the health endpoint:")

    code_block('''@pytest.mark.asyncio
async def test_health_returns_ok(client: AsyncClient):
    resp = await client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert "version" in data

@pytest.mark.asyncio
async def test_health_is_fast(client: AsyncClient):
    """Health check should respond under 50ms."""
    start = time.monotonic()
    await client.get("/health")
    assert time.monotonic() - start < 0.05''')

    tool_call("Edit", "tests/test_api.py")
    time.sleep(0.2)
    success("Applied edit to tests/test_api.py")
    time.sleep(1.5)

    # ── Turn 3 ───────────────────────────────────────────────
    user_prompt("run the tests")
    time.sleep(0.4)

    show_thinking(3.0, ad=ONELINERS[1])

    tool_call("Bash", "pytest tests/test_api.py -v")
    time.sleep(0.4)
    test_output(passed=2, duration=0.34)
    assistant_text("Both tests pass. The health endpoint is working and responds quickly.")
    time.sleep(1.5)

    # ── Turn 4 ───────────────────────────────────────────────
    user_prompt("now add rate limiting to it, 100 req/min per IP")
    time.sleep(0.4)

    show_thinking(5.0, ad=CARDS[1])

    tool_call("Read", "src/main.py")
    time.sleep(0.2)
    tool_call("Read", "pyproject.toml")
    time.sleep(0.2)
    assistant_text("I'll add IP-based rate limiting using slowapi:")

    code_block('''from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter

@app.get("/health")
@limiter.limit("100/minute")
async def health_check(request: Request) -> dict[str, str]:
    return {"status": "ok", "version": app.version}''')

    tool_call("Edit", "src/main.py")
    time.sleep(0.2)
    success("Applied edit to src/main.py")
    tool_call("Bash", "pip install slowapi")
    time.sleep(0.3)
    success("Installed slowapi")
    time.sleep(1.0)

    # ── Footer ───────────────────────────────────────────────
    print()
    print(paint(f"  {hr}", DARK_ASH, DIM))
    print()
    print(paint("  end of simulation", TEAL, BOLD))
    print()
    print(paint("  Design notes:", STONE))
    print(paint("  . Ads appear only during thinking, disappear on response", ASH))
    print(paint("  . Feynman Everforest palette: warm, muted, non-intrusive", ASH))
    print(paint("  . One-liners for short thinks, cards for longer thinks", ASH))
    print(paint("  . Borders dim dark ash, content warm ink", ASH))
    print(paint("  . Ad clears itself via ANSI cursor: zero residue", ASH))
    print()


if __name__ == "__main__":
    run()
