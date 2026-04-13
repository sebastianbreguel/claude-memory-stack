"""Tests for mempatterns.py — PatternDetector."""

from __future__ import annotations

import sqlite3

import pytest

from mempatterns import PatternDetector


@pytest.fixture
def tmp_db(tmp_path):
    """Create a memory.db with schema."""
    db_path = tmp_path / "memory.db"
    conn = sqlite3.connect(str(db_path))
    conn.executescript("""
        CREATE TABLE sessions (
            id INTEGER PRIMARY KEY, session_id TEXT UNIQUE NOT NULL,
            project TEXT NOT NULL, cwd TEXT, branch TEXT, topic TEXT,
            message_count INTEGER DEFAULT 0, tool_count INTEGER DEFAULT 0,
            captured_at TEXT NOT NULL, transcript_path TEXT
        );
        CREATE TABLE files_touched (
            id INTEGER PRIMARY KEY, session_id TEXT NOT NULL,
            path TEXT NOT NULL, action TEXT NOT NULL, count INTEGER DEFAULT 1
        );
        CREATE TABLE facts (
            id INTEGER PRIMARY KEY, session_id TEXT NOT NULL,
            type TEXT NOT NULL, content TEXT NOT NULL, content_hash TEXT NOT NULL,
            source_line INTEGER, created_at TEXT NOT NULL DEFAULT (datetime('now'))
        );
        CREATE TABLE tool_usage (
            id INTEGER PRIMARY KEY, session_id TEXT NOT NULL,
            tool_name TEXT NOT NULL, count INTEGER DEFAULT 1,
            UNIQUE(session_id, tool_name)
        );
    """)
    conn.commit()
    return db_path, conn


@pytest.fixture
def wiki_dir(tmp_path):
    return tmp_path / "patterns"


# ---------------------------------------------------------------------------
# detect_co_edits
# ---------------------------------------------------------------------------


def test_co_edits_above_threshold(tmp_db, wiki_dir):
    db_path, conn = tmp_db
    for i in range(5):
        sid = f"sess-{i}"
        conn.execute(
            "INSERT INTO sessions VALUES (?,?,?,?,?,?,?,?,?,?)",
            (
                i,
                sid,
                "proj",
                None,
                None,
                None,
                0,
                0,
                f"2024-01-0{i + 1}T10:00:00",
                None,
            ),
        )
        conn.execute(
            "INSERT INTO files_touched VALUES (?,?,?,?,?)",
            (i * 2, sid, "a.py", "edit", 1),
        )
        conn.execute(
            "INSERT INTO files_touched VALUES (?,?,?,?,?)",
            (i * 2 + 1, sid, "b.py", "write", 1),
        )
    conn.commit()

    with PatternDetector(db_path=db_path, wiki_dir=wiki_dir) as pd:
        results = pd.detect_co_edits(threshold=5)

    assert len(results) == 1
    assert set(results[0]["files"]) == {"a.py", "b.py"}
    assert results[0]["count"] == 5
    assert results[0]["kind"] == "co_edit"


def test_co_edits_below_threshold_ignored(tmp_db, wiki_dir):
    db_path, conn = tmp_db
    for i in range(3):
        sid = f"sess-{i}"
        conn.execute(
            "INSERT INTO sessions VALUES (?,?,?,?,?,?,?,?,?,?)",
            (
                i,
                sid,
                "proj",
                None,
                None,
                None,
                0,
                0,
                f"2024-01-0{i + 1}T10:00:00",
                None,
            ),
        )
        conn.execute(
            "INSERT INTO files_touched VALUES (?,?,?,?,?)",
            (i * 2, sid, "a.py", "edit", 1),
        )
        conn.execute(
            "INSERT INTO files_touched VALUES (?,?,?,?,?)",
            (i * 2 + 1, sid, "b.py", "edit", 1),
        )
    conn.commit()

    with PatternDetector(db_path=db_path, wiki_dir=wiki_dir) as pd:
        results = pd.detect_co_edits(threshold=5)

    assert results == []


def test_co_edits_readonly_actions_ignored(tmp_db, wiki_dir):
    db_path, conn = tmp_db
    for i in range(6):
        sid = f"sess-{i}"
        conn.execute(
            "INSERT INTO sessions VALUES (?,?,?,?,?,?,?,?,?,?)",
            (
                i,
                sid,
                "proj",
                None,
                None,
                None,
                0,
                0,
                f"2024-01-0{i + 1}T10:00:00",
                None,
            ),
        )
        conn.execute(
            "INSERT INTO files_touched VALUES (?,?,?,?,?)",
            (i * 2, sid, "a.py", "read", 1),
        )
        conn.execute(
            "INSERT INTO files_touched VALUES (?,?,?,?,?)",
            (i * 2 + 1, sid, "b.py", "read", 1),
        )
    conn.commit()

    with PatternDetector(db_path=db_path, wiki_dir=wiki_dir) as pd:
        results = pd.detect_co_edits(threshold=5)

    assert results == []


# ---------------------------------------------------------------------------
# detect_error_recurrence
# ---------------------------------------------------------------------------


def test_error_recurrence_detected(tmp_db, wiki_dir):
    db_path, conn = tmp_db
    for i in range(3):
        sid = f"sess-{i}"
        conn.execute(
            "INSERT INTO sessions VALUES (?,?,?,?,?,?,?,?,?,?)",
            (
                i,
                sid,
                "proj",
                None,
                None,
                None,
                0,
                0,
                f"2024-01-0{i + 1}T10:00:00",
                None,
            ),
        )
        conn.execute(
            "INSERT INTO facts VALUES (?,?,?,?,?,?,?)",
            (
                i,
                sid,
                "error",
                "TypeError: NoneType",
                "hash-abc",
                None,
                f"2024-01-0{i + 1}T10:00:00",
            ),
        )
    conn.commit()

    with PatternDetector(db_path=db_path, wiki_dir=wiki_dir) as pd:
        results = pd.detect_error_recurrence(threshold=3)

    assert len(results) == 1
    assert results[0]["content"] == "TypeError: NoneType"
    assert results[0]["hash"] == "hash-abc"
    assert results[0]["count"] == 3
    assert results[0]["kind"] == "error_recurrence"


def test_error_recurrence_below_threshold_ignored(tmp_db, wiki_dir):
    db_path, conn = tmp_db
    for i in range(2):
        sid = f"sess-{i}"
        conn.execute(
            "INSERT INTO sessions VALUES (?,?,?,?,?,?,?,?,?,?)",
            (
                i,
                sid,
                "proj",
                None,
                None,
                None,
                0,
                0,
                f"2024-01-0{i + 1}T10:00:00",
                None,
            ),
        )
        conn.execute(
            "INSERT INTO facts VALUES (?,?,?,?,?,?,?)",
            (
                i,
                sid,
                "error",
                "TypeError: NoneType",
                "hash-abc",
                None,
                f"2024-01-0{i + 1}T10:00:00",
            ),
        )
    conn.commit()

    with PatternDetector(db_path=db_path, wiki_dir=wiki_dir) as pd:
        results = pd.detect_error_recurrence(threshold=3)

    assert results == []


# ---------------------------------------------------------------------------
# detect_project_streaks
# ---------------------------------------------------------------------------


def test_project_streaks_detected(tmp_db, wiki_dir):
    db_path, conn = tmp_db
    project = "myproject"
    for i in range(5):
        sid = f"sess-{i}"
        day = f"2024-01-{i + 1:02d}"
        conn.execute(
            "INSERT INTO sessions VALUES (?,?,?,?,?,?,?,?,?,?)",
            (i, sid, project, None, None, None, 0, 0, f"{day}T10:00:00", None),
        )
    conn.commit()

    with PatternDetector(db_path=db_path, wiki_dir=wiki_dir) as pd:
        results = pd.detect_project_streaks(threshold=5)

    assert len(results) == 1
    assert results[0]["project"] == project
    assert results[0]["streak"] == 5
    assert results[0]["kind"] == "project_streak"


def test_project_streaks_gap_breaks_streak(tmp_db, wiki_dir):
    db_path, conn = tmp_db
    project = "myproject"
    # Days 1,2,3 — gap — 5,6,7,8,9  (streak of 3 then 5)
    days = [
        "2024-01-01",
        "2024-01-02",
        "2024-01-03",
        "2024-01-05",
        "2024-01-06",
        "2024-01-07",
        "2024-01-08",
        "2024-01-09",
    ]
    for i, day in enumerate(days):
        sid = f"sess-{i}"
        conn.execute(
            "INSERT INTO sessions VALUES (?,?,?,?,?,?,?,?,?,?)",
            (i, sid, project, None, None, None, 0, 0, f"{day}T10:00:00", None),
        )
    conn.commit()

    with PatternDetector(db_path=db_path, wiki_dir=wiki_dir) as pd:
        results = pd.detect_project_streaks(threshold=5)

    assert len(results) == 1
    assert results[0]["streak"] == 5


def test_project_streaks_below_threshold_ignored(tmp_db, wiki_dir):
    db_path, conn = tmp_db
    for i in range(3):
        sid = f"sess-{i}"
        conn.execute(
            "INSERT INTO sessions VALUES (?,?,?,?,?,?,?,?,?,?)",
            (
                i,
                sid,
                "proj",
                None,
                None,
                None,
                0,
                0,
                f"2024-01-0{i + 1}T10:00:00",
                None,
            ),
        )
    conn.commit()

    with PatternDetector(db_path=db_path, wiki_dir=wiki_dir) as pd:
        results = pd.detect_project_streaks(threshold=5)

    assert results == []


# ---------------------------------------------------------------------------
# detect_tool_anomalies
# ---------------------------------------------------------------------------


def test_tool_anomalies_detected(tmp_db, wiki_dir):
    db_path, conn = tmp_db
    # Project A: high Bash usage (avg 100)
    for i in range(3):
        sid = f"sess-a-{i}"
        conn.execute(
            "INSERT INTO sessions VALUES (?,?,?,?,?,?,?,?,?,?)",
            (
                i,
                sid,
                "proj-a",
                None,
                None,
                None,
                0,
                0,
                f"2024-01-0{i + 1}T10:00:00",
                None,
            ),
        )
        conn.execute(
            "INSERT INTO tool_usage VALUES (?,?,?,?)", (i * 2, sid, "Bash", 100)
        )
    # Projects B, C, D: low Bash usage (avg 1) — global avg = (100+1+1+1)/4 = 25.75, ratio proj-a = 100/25.75 > 2
    for proj_idx, proj in enumerate(["proj-b", "proj-c", "proj-d"]):
        for i in range(3):
            sid = f"sess-{proj}-{i}"
            conn.execute(
                "INSERT INTO sessions VALUES (?,?,?,?,?,?,?,?,?,?)",
                (
                    10 + proj_idx * 10 + i,
                    sid,
                    proj,
                    None,
                    None,
                    None,
                    0,
                    0,
                    f"2024-01-0{i + 1}T10:00:00",
                    None,
                ),
            )
            conn.execute(
                "INSERT INTO tool_usage VALUES (?,?,?,?)",
                (50 + proj_idx * 10 + i * 2, sid, "Bash", 1),
            )
    conn.commit()

    with PatternDetector(db_path=db_path, wiki_dir=wiki_dir) as pd:
        results = pd.detect_tool_anomalies(factor=2.0)

    projects = [r["project"] for r in results]
    assert "proj-a" in projects
    anomaly = next(r for r in results if r["project"] == "proj-a")
    assert anomaly["tool"] == "Bash"
    assert anomaly["ratio"] > 2.0
    assert anomaly["kind"] == "tool_anomaly"


def test_tool_anomalies_similar_usage_not_flagged(tmp_db, wiki_dir):
    db_path, conn = tmp_db
    for proj_idx, proj in enumerate(["proj-a", "proj-b", "proj-c"]):
        for i in range(3):
            sid = f"sess-{proj_idx}-{i}"
            conn.execute(
                "INSERT INTO sessions VALUES (?,?,?,?,?,?,?,?,?,?)",
                (
                    proj_idx * 10 + i,
                    sid,
                    proj,
                    None,
                    None,
                    None,
                    0,
                    0,
                    f"2024-01-0{i + 1}T10:00:00",
                    None,
                ),
            )
            conn.execute(
                "INSERT INTO tool_usage VALUES (?,?,?,?)",
                (proj_idx * 10 + i + 1, sid, "Bash", 10),
            )
    conn.commit()

    with PatternDetector(db_path=db_path, wiki_dir=wiki_dir) as pd:
        results = pd.detect_tool_anomalies(factor=2.0)

    assert results == []


# ---------------------------------------------------------------------------
# Context manager
# ---------------------------------------------------------------------------


def test_context_manager_closes_connection(tmp_db, wiki_dir):
    db_path, conn = tmp_db
    conn.commit()

    with PatternDetector(db_path=db_path, wiki_dir=wiki_dir) as pd:
        internal_conn = pd.conn

    # After exit, connection should be closed — cursor ops should fail
    with pytest.raises(Exception):
        internal_conn.execute("SELECT 1")
