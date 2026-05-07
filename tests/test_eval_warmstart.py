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


def test_inject_context_cutoff_filters_post_cutoff_memories(tmp_path):
    """Memories created after cutoff_ts must not appear in the injected text."""
    import sys

    sys.path.insert(0, str(REPO / "tools"))
    import memcapture as mc

    db_path = tmp_path / "memory.db"
    db = mc.MemoryDB(db_path=db_path)
    try:
        # Pre-cutoff memory: explicit older timestamp
        db.conn.execute(
            "INSERT INTO memories (topic, content, durability, created_at) VALUES (?, ?, ?, ?)",
            ("old_pref", "old durable about FTS5 reranking", "durable", "2025-01-01 00:00:00"),
        )
        # Post-cutoff memory: explicit newer timestamp
        db.conn.execute(
            "INSERT INTO memories (topic, content, durability, created_at) VALUES (?, ?, ?, ?)",
            ("new_pref", "new durable about HNSW indexing", "durable", "2026-06-01 00:00:00"),
        )
        db.conn.commit()

        # Cutoff falls between the two memories
        out = db.inject_context(cutoff_ts="2026-01-01 00:00:00")
        assert "FTS5" in out
        assert "HNSW" not in out
    finally:
        db.close()


def test_inject_context_engram_rerank_off_disables_query(tmp_path, monkeypatch):
    """ENGRAM_RERANK=off must change inject ordering when memories compete on relevance."""
    import sys

    sys.path.insert(0, str(REPO / "tools"))
    import memcapture as mc

    db_path = tmp_path / "memory.db"
    db = mc.MemoryDB(db_path=db_path)
    try:
        # Match memory has token "FTS5" matching the query; older but query-aware should rank it first.
        db.conn.execute(
            "INSERT INTO memories (topic, content, durability, created_at, last_accessed) VALUES (?, ?, ?, ?, ?)",
            ("match", "FTS5 reranking notes", "durable", "2024-01-01", "2024-01-01"),
        )
        # Recent unrelated memory; should win on recency when rerank disabled.
        db.conn.execute(
            "INSERT INTO memories (topic, content, durability, created_at, last_accessed) VALUES (?, ?, ?, ?, ?)",
            ("recent", "unrelated docker compose tips", "durable", "2026-04-01", "2026-04-01"),
        )
        db.conn.commit()

        monkeypatch.delenv("ENGRAM_RERANK", raising=False)
        on = db.inject_context(query="FTS5", cutoff_ts="2026-05-01")

        monkeypatch.setenv("ENGRAM_RERANK", "off")
        off = db.inject_context(query="FTS5", cutoff_ts="2026-05-01")

        # With rerank ON, the FTS5-match memory should outrank the recent one.
        assert on.find("FTS5 reranking") < on.find("docker compose")
        # With rerank OFF, recency wins — recent memory appears first.
        assert off.find("docker compose") < off.find("FTS5 reranking")
    finally:
        db.close()


def test_inject_context_cutoff_is_read_only(tmp_path):
    """cutoff_ts mode must not bump last_accessed or insert into injections."""
    import sys

    sys.path.insert(0, str(REPO / "tools"))
    import memcapture as mc

    db_path = tmp_path / "memory.db"
    db = mc.MemoryDB(db_path=db_path)
    try:
        db.conn.execute(
            "INSERT INTO memories (topic, content, durability, created_at, last_accessed) VALUES (?, ?, ?, ?, ?)",
            ("p", "alpha bravo charlie", "durable", "2025-01-01 00:00:00", "2025-01-01 00:00:00"),
        )
        db.conn.commit()

        db.inject_context(session_id="sess-eval", cutoff_ts="2026-01-01 00:00:00")

        la = db.conn.execute("SELECT last_accessed FROM memories WHERE topic = ?", ("p",)).fetchone()[0]
        assert la == "2025-01-01 00:00:00"
        injected = db.conn.execute("SELECT COUNT(*) FROM injections WHERE session_id = ?", ("sess-eval",)).fetchone()[0]
        assert injected == 0
    finally:
        db.close()
