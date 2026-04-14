"""CLI surface tests for engram.py."""

from __future__ import annotations

import json as _json
import subprocess
from pathlib import Path

REPO = Path(__file__).parent.parent
ENGRAM = REPO / "tools" / "engram.py"


def _run(args: list[str], **kw) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["uv", "run", str(ENGRAM), *args],
        cwd=str(REPO),
        capture_output=True,
        text=True,
        timeout=30,
        **kw,
    )


def test_help_lists_all_subcommands():
    result = _run(["--help"])
    assert result.returncode == 0
    for cmd in [
        "capture",
        "inject",
        "digest",
        "snapshot",
        "patterns",
        "dashboard",
        "compile",
        "export-concepts",
        "stats",
        "memories",
        "forget",
        "on-precompact",
        "on-session-start",
    ]:
        assert cmd in result.stdout, f"missing subcommand in help: {cmd}"


def test_stats_runs(tmp_path, monkeypatch):
    fake_home = tmp_path / "home"
    (fake_home / ".claude").mkdir(parents=True)
    monkeypatch.setenv("HOME", str(fake_home))
    result = _run(["stats"])
    assert result.returncode == 0


def test_inject_runs(tmp_path, monkeypatch):
    fake_home = tmp_path / "home"
    (fake_home / ".claude").mkdir(parents=True)
    monkeypatch.setenv("HOME", str(fake_home))
    result = _run(["inject"])
    assert result.returncode == 0


def test_on_session_start_emits_valid_json(tmp_path, monkeypatch):
    fake_home = tmp_path / "home"
    (fake_home / ".claude").mkdir(parents=True)
    monkeypatch.setenv("HOME", str(fake_home))
    payload = _json.dumps({"cwd": str(tmp_path)})
    result = _run(["on-session-start"], input=payload)
    assert result.returncode == 0
    out = _json.loads(result.stdout)
    assert out.get("continue") is True
    assert out.get("hookSpecificOutput", {}).get("hookEventName") == "SessionStart"


def test_on_precompact_captures_session(tmp_path, monkeypatch):
    """on-precompact: reads session_id from stdin, captures transcript, skips LLM in test mode."""
    fake_home = tmp_path / "home"
    proj_dir = fake_home / ".claude" / "projects" / "test-proj"
    proj_dir.mkdir(parents=True)
    transcript = proj_dir / "abc123.jsonl"
    transcript.write_text(
        '{"type":"user","message":{"content":"hello"}}\n{"type":"assistant","message":{"content":[{"type":"text","text":"hi"}]}}\n'
    )
    monkeypatch.setenv("HOME", str(fake_home))
    monkeypatch.setenv("ENGRAM_SKIP_LLM", "1")
    payload = _json.dumps({"session_id": "abc123"})
    result = _run(["on-precompact"], input=payload)
    assert result.returncode == 0, f"on-precompact failed: {result.stderr}"


def test_hooks_json_uses_engram_inline():
    """After Task 8, hooks.json references engram.py, not .sh."""
    config = _json.loads((REPO / "hooks" / "hooks.json").read_text())
    for event in ("PreCompact", "SessionStart"):
        for entry in config.get("hooks", {}).get(event, []):
            for h in entry.get("hooks", []):
                cmd = h.get("command", "")
                assert "engram.py" in cmd, f"hook should reference engram.py: {cmd}"
                assert ".sh" not in cmd, f"hook should not reference a shell script: {cmd}"
