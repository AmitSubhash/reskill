from __future__ import annotations

from reskill import pacing, quiz_panel, scheduler
from reskill import state as state_mod
from reskill.question import Option, Question

NOW = 1_000_000.0


def _q(prompt: str, concept: str) -> Question:
    return Question(
        prompt=prompt,
        options=[Option("1", "ok", True)],
        explanation="x",
        concept=concept,
    )


def test_quiz_loop_retry_escapes_blocked_fallback_concept(monkeypatch):
    blocked = _q("blocked", "caching")
    alternative = _q("alternative", "async")

    monkeypatch.setattr(
        scheduler,
        "TEMPLATE_BANK",
        {
            "lru_cache": [blocked],
            "async_def": [alternative],
        },
    )
    monkeypatch.setattr(scheduler, "detect_concepts", lambda text: [])
    monkeypatch.setattr(
        scheduler.random,
        "sample",
        lambda seq, k: list(seq),
    )
    monkeypatch.setattr(scheduler.time, "time", lambda: NOW)
    monkeypatch.setattr(pacing.time, "time", lambda: NOW)
    monkeypatch.setattr(quiz_panel, "recent_transcript_text", lambda cwd=None: "")
    monkeypatch.setattr(quiz_panel, "fetch_commits", lambda *args, **kwargs: [])
    monkeypatch.setattr(quiz_panel, "project_root", lambda: None)
    monkeypatch.setattr(quiz_panel, "_render_cooldown_card", lambda *args: None)
    monkeypatch.setattr(quiz_panel, "_render_take_a_breath", lambda: None)
    monkeypatch.setattr(quiz_panel, "_arming_pulse", lambda: None)
    monkeypatch.setattr(quiz_panel, "_render_question_view", lambda *args: None)
    monkeypatch.setattr(quiz_panel, "_is_thinking_with_grace", lambda: False)
    monkeypatch.setattr(quiz_panel.time, "sleep", lambda _: None)
    monkeypatch.setattr(pacing, "save", lambda ps: None)

    state = state_mod.State()
    state.concepts["caching"] = {
        "ef": 2.5,
        "interval": 30,
        "reps": 1,
        "last": NOW,
        "correct": 1,
        "total": 1,
    }
    state.concepts["async"] = {
        "ef": 2.5,
        "interval": 30,
        "reps": 1,
        "last": NOW,
        "correct": 1,
        "total": 1,
    }
    paced = pacing.PacingState(
        last_quiz_finished_at=NOW - pacing.MIN_SECONDS_BETWEEN_QUIZZES - 5,
        last_concept_at={"caching": NOW - 1},
    )

    served = quiz_panel._quiz_loop_once(
        state=state,
        session=quiz_panel.SessionCounters(),
        paced=paced,
        review=quiz_panel.ReviewQueue(),
        last_concept="caching",
        recent_formats=[],
    )

    assert served == "async"
