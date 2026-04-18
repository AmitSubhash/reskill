"""Regression tests for Claude Code hook installation shape."""

from __future__ import annotations

import json

from reskill import hookinstall


def _configure_paths(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(hookinstall, "SETTINGS_PATH", tmp_path / "settings.json")
    monkeypatch.setattr(
        hookinstall, "WRAPPER_SCRIPT_PATH", tmp_path / "reskill-statusline-wrapper.sh"
    )
    monkeypatch.setattr(hookinstall, "_find_reskill_binary", lambda: "/opt/homebrew/bin/reskill")


def test_install_moves_reskill_hooks_under_hooks_object(monkeypatch, tmp_path):
    _configure_paths(monkeypatch, tmp_path)

    legacy_settings = {
        "hooks": {
            "PreToolUse": [
                {
                    "matcher": "Bash",
                    "hooks": [{"type": "command", "command": "echo existing-pre"}],
                }
            ]
        },
        "Stop": [
            {
                "matcher": "*",
                "hooks": [
                    {
                        "type": "command",
                        "command": "/opt/homebrew/bin/reskill log-session 2>>/tmp/reskill-hook.log",
                        "timeout": 10,
                        "async": True,
                    }
                ],
            }
        ],
        "UserPromptSubmit": [
            {
                "matcher": "*",
                "hooks": [
                    {
                        "type": "command",
                        "command": (
                            f"mkdir -p {hookinstall.STATE_DIR} && "
                            f"touch {hookinstall.THINKING_FILE} # {hookinstall.THINKING_MARKER}"
                        ),
                        "timeout": 2,
                        "async": True,
                    }
                ],
            }
        ],
    }
    hookinstall.SETTINGS_PATH.write_text(json.dumps(legacy_settings))

    assert hookinstall.install(with_statusline=False) == 0

    saved = json.loads(hookinstall.SETTINGS_PATH.read_text())
    assert "Stop" not in saved
    assert "UserPromptSubmit" not in saved

    hooks = saved["hooks"]
    assert hooks["PreToolUse"][0] == {
        "matcher": "Bash",
        "hooks": [{"type": "command", "command": "echo existing-pre"}],
    }

    pre_reskill = [
        entry
        for entry in hooks["PreToolUse"]
        if entry["hooks"][0]["command"] == hookinstall.THINKING_ON_COMMAND
    ]
    post_reskill = [
        entry
        for entry in hooks["PostToolUse"]
        if entry["hooks"][0]["command"] == hookinstall.THINKING_OFF_COMMAND
    ]
    prompt_reskill = [
        entry
        for entry in hooks["UserPromptSubmit"]
        if entry["hooks"][0]["command"] == hookinstall.THINKING_ON_COMMAND
    ]
    stop_reskill = [
        entry
        for entry in hooks["Stop"]
        if hookinstall._is_reskill_hook(entry["hooks"][0])
    ]

    assert pre_reskill == [{"matcher": "*", "hooks": [hookinstall._build_thinking_on_hook()]}]
    assert post_reskill == [{"matcher": "*", "hooks": [hookinstall._build_thinking_off_hook()]}]
    assert prompt_reskill == [{"hooks": [hookinstall._build_thinking_on_hook()]}]
    assert all("matcher" not in entry for entry in prompt_reskill)
    assert len(stop_reskill) == 2
    assert all("matcher" not in entry for entry in stop_reskill)


def test_uninstall_removes_only_reskill_hooks_from_nested_and_legacy_entries(monkeypatch, tmp_path):
    _configure_paths(monkeypatch, tmp_path)

    settings = {
        "hooks": {
            "PreToolUse": [
                {
                    "matcher": "Bash",
                    "hooks": [{"type": "command", "command": "echo existing-pre"}],
                },
                {"matcher": "*", "hooks": [hookinstall._build_thinking_on_hook()]},
            ],
            "Stop": [
                {"hooks": [hookinstall._build_log_hook()]},
                {"hooks": [{"type": "command", "command": "echo existing-stop"}]},
            ],
        },
        "PostToolUse": [
            {"matcher": "*", "hooks": [hookinstall._build_thinking_off_hook()]},
            {"matcher": "*", "hooks": [{"type": "command", "command": "echo legacy-other"}]},
        ],
        "statusLine": {
            "type": "command",
            "command": "/opt/homebrew/bin/reskill statusline",
        },
    }
    hookinstall.SETTINGS_PATH.write_text(json.dumps(settings))

    assert hookinstall.uninstall() == 0

    saved = json.loads(hookinstall.SETTINGS_PATH.read_text())
    assert saved["hooks"]["PreToolUse"] == [
        {
            "matcher": "Bash",
            "hooks": [{"type": "command", "command": "echo existing-pre"}],
        }
    ]
    assert saved["hooks"]["Stop"] == [
        {"hooks": [{"type": "command", "command": "echo existing-stop"}]}
    ]
    assert saved["PostToolUse"] == [
        {"matcher": "*", "hooks": [{"type": "command", "command": "echo legacy-other"}]}
    ]
    assert "statusLine" not in saved
