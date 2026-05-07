"""Tests for eval_warmstart token-overlap and JSONL parsing helpers."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

REPO = Path(__file__).parent.parent
EVAL = REPO / "tools" / "eval_warmstart.py"


def _load_mod():
    spec = importlib.util.spec_from_file_location("eval_warmstart", EVAL)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_tokens_drops_stopwords_and_short():
    mod = _load_mod()
    out = mod._tokens("The quick brown fox jumps over the lazy dog and a cat")
    assert "quick" in out
    assert "brown" in out
    assert "lazy" in out
    assert "the" not in out
    assert "and" not in out
    assert "a" not in out  # too short


def test_tokens_lowercases_and_strips_punct():
    mod = _load_mod()
    out = mod._tokens("Schema-V4! Migration; UNIQUE(topic) dropped")
    assert "schema" in out
    assert "migration" in out
    assert "topic" in out
    assert "dropped" in out


def test_overlap_ratio_basic():
    mod = _load_mod()
    user = {"schema", "migration", "patterns"}
    inject = {"schema", "migration", "executive", "cache"}
    # 2 of 3 user tokens are in inject = 0.667
    assert abs(mod._overlap_ratio(user, inject) - 2 / 3) < 1e-6


def test_overlap_ratio_empty_user_returns_zero():
    mod = _load_mod()
    assert mod._overlap_ratio(set(), {"a", "b"}) == 0.0


def test_overlap_ratio_empty_inject_returns_zero():
    mod = _load_mod()
    assert mod._overlap_ratio({"a"}, set()) == 0.0


def test_first_user_messages_skips_reminders_and_commands(tmp_path):
    mod = _load_mod()
    transcript = tmp_path / "session.jsonl"
    rows = [
        {"type": "user", "message": {"content": "<command-name>/foo</command-name>"}},
        {"type": "user", "message": {"content": "<system-reminder>noise</system-reminder>"}},
        {"type": "user", "message": {"content": "real first message about schema v4"}},
        {"type": "assistant", "message": {"content": "ok"}},
        {"type": "user", "message": {"content": "second real user message about FTS5"}},
    ]
    transcript.write_text("\n".join(json.dumps(r) for r in rows))

    out = mod._first_user_messages(transcript, n=3)
    assert len(out) == 2
    assert "schema v4" in out[0]
    assert "FTS5" in out[1]


def test_first_user_messages_handles_list_content(tmp_path):
    mod = _load_mod()
    transcript = tmp_path / "session.jsonl"
    rows = [
        {
            "type": "user",
            "message": {"content": [{"type": "text", "text": "list-block message about memdoctor"}]},
        },
        {
            "type": "user",
            "message": {"content": [{"type": "tool_result", "content": "ignored"}]},
        },
    ]
    transcript.write_text("\n".join(json.dumps(r) for r in rows))

    out = mod._first_user_messages(transcript, n=3)
    assert len(out) == 1
    assert "memdoctor" in out[0]


def test_first_user_messages_caps_at_n(tmp_path):
    mod = _load_mod()
    transcript = tmp_path / "session.jsonl"
    rows = [{"type": "user", "message": {"content": f"message number {i} long enough"}} for i in range(10)]
    transcript.write_text("\n".join(json.dumps(r) for r in rows))

    out = mod._first_user_messages(transcript, n=3)
    assert len(out) == 3
