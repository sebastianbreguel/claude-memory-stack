"""Tests for the F1 negative-feedback loop:

- inject_context logs (session_id, topic) into the v3 `injections` table
- detect_negative_attribution flags topics injected into correction-flagged sessions
- _analyze_attribution aggregates per-topic implicated-session counts
- memdoctor.run(negative=True) and run(propose=True, negative=True) wire correctly
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest


@pytest.fixture
def db(tmp_path: Path):
    import memcapture

    db_path = tmp_path / "memory.db"
    d = memcapture.MemoryDB(db_path=db_path)
    yield d
    d.conn.close()


def _seed_memory(d, topic: str, content: str = "x", durability: str = "durable", exposure: int = 0):
    d.conn.execute(
        "INSERT INTO memories (topic, content, durability, exposure_count) VALUES (?, ?, ?, ?)",
        (topic, content, durability, exposure),
    )
    d.conn.commit()


# ---- U2: inject_context logs into injections ----


def test_inject_context_logs_kept_topics(db):
    _seed_memory(db, "rule_a")
    _seed_memory(db, "rule_b")

    db.inject_context(session_id="sess-001")

    rows = db.conn.execute("SELECT session_id, topic FROM injections ORDER BY topic").fetchall()
    topics = [r["topic"] for r in rows]
    assert "rule_a" in topics
    assert "rule_b" in topics
    assert all(r["session_id"] == "sess-001" for r in rows)


def test_inject_context_no_session_id_skips_log(db):
    _seed_memory(db, "rule_a")
    db.inject_context()
    n = db.conn.execute("SELECT COUNT(*) FROM injections").fetchone()[0]
    assert n == 0


def test_inject_context_idempotent_per_session(db):
    _seed_memory(db, "rule_a")
    db.inject_context(session_id="sess-002")
    db.inject_context(session_id="sess-002")  # repeat
    n = db.conn.execute("SELECT COUNT(*) FROM injections WHERE topic='rule_a'").fetchone()[0]
    assert n == 1  # composite PK + INSERT OR IGNORE


def test_inject_context_empty_memories_inserts_nothing(db):
    # No memories seeded → fallback path → no kept_topics → no insert
    db.inject_context(session_id="sess-003")
    n = db.conn.execute("SELECT COUNT(*) FROM injections").fetchone()[0]
    assert n == 0


# ---- U3: detect_negative_attribution + _analyze_attribution ----


def _correction_events():
    return [
        {"type": "user", "message": {"content": "no, that's wrong"}, "timestamp": "2026-05-05T10:00:00Z"},
        {"type": "user", "message": {"content": "wrong again"}, "timestamp": "2026-05-05T10:00:30Z"},
        {"type": "user", "message": {"content": "actually, do this"}, "timestamp": "2026-05-05T10:01:00Z"},
    ]


def _clean_events():
    return [
        {"type": "user", "message": {"content": "please add a function"}, "timestamp": "2026-05-05T10:00:00Z"},
        {"type": "user", "message": {"content": "looks good"}, "timestamp": "2026-05-05T10:00:30Z"},
    ]


def test_detect_negative_attribution_flagged_session_returns_topics(db):
    import memdoctor

    _seed_memory(db, "rule_a")
    _seed_memory(db, "rule_b")
    db.inject_context(session_id="sess-100")

    result = memdoctor.detect_negative_attribution(_correction_events(), "sess-100", db.conn)
    assert set(result.keys()) == {"rule_a", "rule_b"}
    assert all(v == 1 for v in result.values())


def test_detect_negative_attribution_clean_session_returns_empty(db):
    import memdoctor

    _seed_memory(db, "rule_a")
    db.inject_context(session_id="sess-200")
    result = memdoctor.detect_negative_attribution(_clean_events(), "sess-200", db.conn)
    assert result == {}


def test_detect_negative_attribution_no_injections_returns_empty(db):
    import memdoctor

    # flagged session but no rows in injections (e.g., pre-v3 session)
    result = memdoctor.detect_negative_attribution(_correction_events(), "sess-no-rows", db.conn)
    assert result == {}


def test_detect_negative_attribution_empty_session_id(db):
    import memdoctor

    result = memdoctor.detect_negative_attribution(_correction_events(), "", db.conn)
    assert result == {}


def test_analyze_attribution_missing_db_returns_empty(tmp_path):
    import memdoctor

    missing = tmp_path / "nope.db"
    assert memdoctor._analyze_attribution(db_path=missing) == {}


# ---- U4: memdoctor.run(negative=...) integration ----


def test_run_negative_empty_db_prints_no_attributions(tmp_path, monkeypatch, capsys):
    import memdoctor

    fake_home = tmp_path / "home"
    (fake_home / ".claude").mkdir(parents=True)
    monkeypatch.setenv("HOME", str(fake_home))
    monkeypatch.setattr(memdoctor, "MEMORY_DB", fake_home / ".claude" / "memory.db")
    monkeypatch.setattr(memdoctor, "PROJECTS_DIR", fake_home / ".claude" / "projects")

    rc = memdoctor.run(negative=True)
    out = capsys.readouterr().out
    assert rc == 0
    assert "no negative attributions" in out


def test_run_negative_json_payload_shape(tmp_path, monkeypatch, capsys):
    import json as _json

    import memdoctor

    fake_home = tmp_path / "home"
    (fake_home / ".claude").mkdir(parents=True)
    monkeypatch.setenv("HOME", str(fake_home))
    monkeypatch.setattr(memdoctor, "MEMORY_DB", fake_home / ".claude" / "memory.db")
    monkeypatch.setattr(memdoctor, "PROJECTS_DIR", fake_home / ".claude" / "projects")

    rc = memdoctor.run(negative=True, json=True)
    out = capsys.readouterr().out
    assert rc == 0
    payload = _json.loads(out)
    assert "negative_attributions" in payload
    assert "threshold" in payload
    assert payload["threshold"] == memdoctor.MIN_NEGATIVE_SESSIONS


def test_apply_negative_downweight_decrements_floor(tmp_path, monkeypatch):
    import memcapture
    import memdoctor

    db_path = tmp_path / "memory.db"
    d = memcapture.MemoryDB(db_path=db_path)
    try:
        _seed_memory(d, "rule_a", exposure=2)
        _seed_memory(d, "rule_b", exposure=0)  # floor test
        _seed_memory(d, "rule_below", exposure=5)
    finally:
        d.conn.close()

    monkeypatch.setattr("builtins.input", lambda _prompt: "y")
    attributions = {"rule_a": 3, "rule_b": 2, "rule_below": 1}  # rule_below < threshold
    n = memdoctor._apply_negative_downweight(attributions, db_path=db_path)
    assert n == 2  # rule_a + rule_b applied; rule_below skipped

    conn = sqlite3.connect(str(db_path))
    try:
        rows = {r[0]: r[1] for r in conn.execute("SELECT topic, exposure_count FROM memories")}
    finally:
        conn.close()
    assert rows["rule_a"] == 1  # 2 - 1
    assert rows["rule_b"] == 0  # MAX(0, 0-1) = 0 (floor)
    assert rows["rule_below"] == 5  # untouched (below threshold)


def test_apply_negative_downweight_user_declines(tmp_path, monkeypatch):
    import memcapture
    import memdoctor

    db_path = tmp_path / "memory.db"
    d = memcapture.MemoryDB(db_path=db_path)
    try:
        _seed_memory(d, "rule_a", exposure=3)
    finally:
        d.conn.close()

    monkeypatch.setattr("builtins.input", lambda _prompt: "n")
    n = memdoctor._apply_negative_downweight({"rule_a": 5}, db_path=db_path)
    assert n == 0

    conn = sqlite3.connect(str(db_path))
    try:
        ec = conn.execute("SELECT exposure_count FROM memories WHERE topic='rule_a'").fetchone()[0]
    finally:
        conn.close()
    assert ec == 3  # untouched
