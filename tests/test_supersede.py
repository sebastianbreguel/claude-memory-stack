"""Tests for U3: DB-side supersede on content drift.

upsert_memory must:
- INSERT a new row when no current row exists for the topic.
- UPDATE in place (no supersede) when content matches after whitespace normalization.
- INSERT new + mark old.superseded_by = new.id when content drifts.
- Keep current SELECTs (inject_context, list_memories) filtering superseded rows.
- Preserve F1 attribution path (injections table) across supersede chains.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "tools"))

from memcapture import MemoryDB  # noqa: E402


@pytest.fixture
def db(tmp_path):
    d = MemoryDB(db_path=tmp_path / "memory.db")
    yield d
    d.conn.close()


def _all_rows(db):
    return list(db.conn.execute("SELECT id, topic, content, superseded_by FROM memories ORDER BY id").fetchall())


def test_upsert_first_time_inserts(db):
    db.upsert_memory("rule_a", "first content", "durable")
    rows = _all_rows(db)
    assert len(rows) == 1
    assert rows[0]["content"] == "first content"
    assert rows[0]["superseded_by"] is None


def test_upsert_same_content_updates_in_place(db):
    db.upsert_memory("rule_a", "stable content", "durable")
    first_id = _all_rows(db)[0]["id"]
    db.upsert_memory("rule_a", "stable content", "durable")
    rows = _all_rows(db)
    assert len(rows) == 1, "same content must not create supersede chain"
    assert rows[0]["id"] == first_id


def test_upsert_whitespace_only_diff_treated_as_same(db):
    db.upsert_memory("rule_a", "hello  world", "durable")
    db.upsert_memory("rule_a", " hello world\n", "durable")
    rows = _all_rows(db)
    assert len(rows) == 1, "whitespace-only diff must not create supersede chain"


def test_upsert_content_drift_creates_supersede_chain(db):
    db.upsert_memory("rule_a", "old content", "durable")
    old_id = _all_rows(db)[0]["id"]
    db.upsert_memory("rule_a", "new content", "durable")
    rows = _all_rows(db)
    assert len(rows) == 2
    by_id = {r["id"]: r for r in rows}
    new_id = next(r["id"] for r in rows if r["id"] != old_id)
    assert by_id[old_id]["superseded_by"] == new_id, "old row must point at new"
    assert by_id[new_id]["superseded_by"] is None, "new row is current"
    assert by_id[old_id]["content"] == "old content", "audit trail preserved"
    assert by_id[new_id]["content"] == "new content"


def test_three_deep_supersede_chain(db):
    db.upsert_memory("x", "v1", "durable")
    db.upsert_memory("x", "v2", "durable")
    db.upsert_memory("x", "v3", "durable")
    rows = _all_rows(db)
    assert len(rows) == 3
    current = [r for r in rows if r["superseded_by"] is None]
    assert len(current) == 1
    assert current[0]["content"] == "v3"
    # Each older row points at a newer one
    superseded = [r for r in rows if r["superseded_by"] is not None]
    assert len(superseded) == 2


def test_inject_context_excludes_superseded_rows(db):
    db.upsert_memory("rule_a", "old", "durable")
    db.upsert_memory("rule_a", "new", "durable")
    chunk = db.inject_context()
    assert "new" in chunk
    assert "old" not in chunk


def test_list_memories_excludes_superseded_rows(db):
    db.upsert_memory("rule_a", "v1", "durable")
    db.upsert_memory("rule_a", "v2", "durable")
    listed = db.list_memories()
    assert len(listed) == 1
    assert listed[0]["content"] == "v2"


def test_supersede_preserves_f1_injections_attribution(db):
    """F1 references topics by name (no FK to memories.id). After a supersede
    chain, the injections row still maps to the *current* row at decrement time
    because the F1 path SELECTs by topic + superseded_by IS NULL.
    """
    db.upsert_memory("rule_a", "original", "durable")
    db.inject_context(session_id="sess-001")
    # drift the memory after injection
    db.upsert_memory("rule_a", "revised content", "durable")
    inj_rows = list(db.conn.execute("SELECT session_id, topic FROM injections").fetchall())
    assert len(inj_rows) == 1
    assert inj_rows[0]["topic"] == "rule_a"
    # current memory is the revised one
    current = list(db.conn.execute("SELECT content FROM memories WHERE topic='rule_a' AND superseded_by IS NULL").fetchall())
    assert len(current) == 1
    assert current[0]["content"] == "revised content"
