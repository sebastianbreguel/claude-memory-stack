"""End-to-end contract tests — lock user-visible behavior.

These tests assert on stdout, exit codes, and injected context strings. They do
NOT assert on SQLite column contents or row counts — schema is internal.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

FIXTURE = Path(__file__).parent / "fixtures" / "sample_transcript.jsonl"
REPO = Path(__file__).parent.parent


@pytest.fixture
def tmp_home(tmp_path, monkeypatch):
    """Isolate ~/.claude to a tmp dir per test."""
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    (fake_home / ".claude").mkdir()
    monkeypatch.setenv("HOME", str(fake_home))
    return fake_home


_FLAG_TO_SUBCMD = {
    "--stats": ["stats"],
    "--memories": ["memories"],
    "--inject": ["inject"],
    "--ingest-digest": ["digest"],
    "--ingest-snapshot": ["snapshot"],
}


def _translate(args: list[str]) -> list[str]:
    """Translate legacy memcapture flags to engram subcommand form."""
    if not args:
        return args
    head = args[0]
    rest = args[1:]
    if head == "--transcript":
        return ["capture", "--transcript", *rest]
    if head == "--inject" and "--inject-project" in rest:
        i = rest.index("--inject-project")
        return ["inject", "--project", rest[i + 1], *rest[:i], *rest[i + 2 :]]
    if head in _FLAG_TO_SUBCMD:
        return [*_FLAG_TO_SUBCMD[head], *rest]
    return args


def _memcap(args: list[str], **kw) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["uv", "run", str(REPO / "tools" / "engram.py"), *_translate(args)],
        cwd=str(REPO),
        capture_output=True,
        text=True,
        timeout=60,
        **kw,
    )


def test_capture_transcript_exits_zero(tmp_home):
    """Feeding a transcript succeeds — no crash, no schema assertion."""
    result = _memcap(["--transcript", str(FIXTURE)])
    assert result.returncode == 0, f"capture failed: {result.stderr}"


def test_schema_user_version_is_3(tmp_home):
    """PRAGMA user_version is stamped to 3 after any capture (v3 baseline).

    Future schema changes must bump this in `_migrate` and gate their ALTERs
    behind `if version < N:` blocks. This test locks the baseline.
    """
    import sqlite3

    _memcap(["--transcript", str(FIXTURE)])
    db_path = tmp_home / ".claude" / "memory.db"
    assert db_path.exists(), "memory.db should exist after capture"
    conn = sqlite3.connect(str(db_path))
    try:
        version = conn.execute("PRAGMA user_version").fetchone()[0]
        tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    finally:
        conn.close()
    assert version == 3, f"expected user_version=3, got {version}"
    assert "injections" in tables, "v3 must create injections table"


def test_migrate_refuses_future_schema_version(tmp_path):
    """If user_version on disk exceeds LATEST_SCHEMA_VERSION, _migrate must
    refuse — silently using a future schema risks data loss after a downgrade.

    Uses tmp_path (not tmp_home) on purpose: the file name is `engram_test.db`,
    not `memory.db`, so even if memcapture's module-level DB_PATH happens to
    point inside tmp_path, there is no collision with this fixture file.
    """
    import sqlite3
    import sys

    sys.path.insert(0, str(REPO / "tools"))
    from memcapture import MemoryDB

    db_path = tmp_path / "engram_test.db"
    conn = sqlite3.connect(str(db_path))
    conn.execute(f"PRAGMA user_version = {MemoryDB.LATEST_SCHEMA_VERSION + 1}")
    conn.commit()
    conn.close()

    with pytest.raises(RuntimeError, match="newer than this engram"):
        MemoryDB(db_path=db_path)


def test_capture_then_stats_reports_activity(tmp_home):
    """After capture, --stats reports non-zero sessions. Contract: the user sees a summary."""
    _memcap(["--transcript", str(FIXTURE)])
    result = _memcap(["--stats"])
    assert result.returncode == 0
    combined = result.stdout + result.stderr
    assert "session" in combined.lower(), f"stats should mention sessions: {combined!r}"


def test_ingest_digest_then_inject_surfaces_the_memory(tmp_home):
    """End-to-end contract: a digest line about `uv` appears in injected context.

    This is the core user-visible promise of engram: what the LLM learned comes
    back in the next SessionStart context.
    """
    # Capture a session (needed so --ingest-digest has a session_id to attach to).
    _memcap(["--transcript", str(FIXTURE)])

    digest_text = (
        "package_manager | durable | prefers uv over pip\n"
        "current_refactor | ephemeral | removing Docker references from repo\n"
        "\n"
        "HANDOFF: we decided to use uv and drop Docker. Next session should verify install.sh."
    )
    ingest = _memcap(
        ["--ingest-digest", "--session-id", "test-session", "--project", "engram-test"],
        input=digest_text,
    )
    assert ingest.returncode == 0, f"ingest failed: {ingest.stderr}"

    # Contract: the memory surfaces in the injected context string.
    inject = _memcap(["--inject"])
    assert inject.returncode == 0
    assert "uv" in inject.stdout.lower(), f"expected 'uv' in injected context, got: {inject.stdout!r}"


def test_project_scoped_inject_surfaces_handoff(tmp_home):
    """A project-scoped digest with a HANDOFF surfaces when --inject-project matches."""
    _memcap(["--transcript", str(FIXTURE)])
    digest = "test_topic | ephemeral | working on auth refactor\n\nHANDOFF: halfway through extracting auth middleware into its own module."
    _memcap(
        ["--ingest-digest", "--session-id", "s1", "--project", "my-project"],
        input=digest,
    )
    result = _memcap(["--inject", "--inject-project", "my-project"])
    assert result.returncode == 0
    # Handoff content should reach the user's context. Exact wording/placement is free.
    assert "auth" in result.stdout.lower(), f"project-scoped handoff should surface, got: {result.stdout!r}"


def test_semantic_error_regex_removed_from_module():
    """Task 4 contract: the regex lists that distinguish 'real errors' from
    'code mentioning errors' are gone. The LLM digest handles semantic judgment.

    Fails against current code (both attrs exist), passes after Task 4 deletes them.
    """
    import importlib

    memcap = importlib.import_module("memcapture")
    assert not hasattr(memcap, "ACTUAL_ERROR_PATTERNS"), "ACTUAL_ERROR_PATTERNS should be removed — LLM digest handles error judgment"
    assert not hasattr(memcap, "ERROR_FALSE_POSITIVES"), "ERROR_FALSE_POSITIVES should be removed — no longer needed without regex matching"


def test_non_error_tool_result_with_traceback_does_not_capture_fact(tmp_home, tmp_path):
    """Task 4 behavioral contract: a tool_result with is_error=False containing a
    Traceback string should NOT produce a facts.type='error' row.

    Current code matches ACTUAL_ERROR_PATTERNS on the Traceback line and captures it.
    After Task 4, only is_error=True triggers capture. LLM digest handles the rest.
    """
    import sqlite3

    fake_transcript = tmp_path / "fake.jsonl"
    fake_transcript.write_text(
        json.dumps({"type": "user", "message": {"content": "run the script please"}})
        + "\n"
        + json.dumps(
            {
                "type": "assistant",
                "message": {"content": [{"type": "text", "text": "running the script now"}]},
            }
        )
        + "\n"
        + json.dumps(
            {
                "type": "user",
                "message": {
                    "content": [
                        {
                            "type": "tool_result",
                            "content": "Traceback (most recent call last):\n  File \"/tmp/x.py\", line 3, in <module>\n    raise ValueError('demo')",
                            "is_error": False,
                        }
                    ]
                },
            }
        )
        + "\n"
    )
    result = _memcap(["--transcript", str(fake_transcript)])
    assert result.returncode == 0

    db = tmp_home / ".claude" / "memory.db"
    conn = sqlite3.connect(str(db))
    error_facts = conn.execute("SELECT content FROM facts WHERE type='error'").fetchall()
    conn.close()
    assert error_facts == [], f"non-error tool_result should not produce error facts, got: {error_facts!r}"


def test_facts_table_has_typed_columns(tmp_home):
    """v1 schema widen: facts has nullable subject/predicate/object/confidence.

    v1 never populates them. v2 will. This test guards that the columns exist.
    """
    import sqlite3

    _memcap(["--transcript", str(FIXTURE)])
    db = tmp_home / ".claude" / "memory.db"
    conn = sqlite3.connect(str(db))
    cols = {row[1] for row in conn.execute("PRAGMA table_info(facts)").fetchall()}
    conn.close()
    assert {"subject", "predicate", "object", "confidence"}.issubset(cols), f"facts table missing typed columns, has: {cols}"


def test_parse_digest_dedupes_duplicate_topics_in_batch(tmp_home):
    """Same topic twice in one batch → last-wins, single row. Guards the race window
    where Haiku emits the same topic with different content in one call."""
    _memcap(["--transcript", str(FIXTURE)])
    digest = "package_manager | durable | prefers uv\npackage_manager | durable | prefers uv over pip strictly\n"
    _memcap(["--ingest-digest", "--session-id", "s1", "--project", "p1"], input=digest)
    memories = _memcap(["--memories"]).stdout
    assert memories.count("prefers uv") == 1, f"duplicate topic should collapse: {memories!r}"
    assert "prefers uv over pip strictly" in memories, "last line should win"


def test_ingest_digest_is_idempotent(tmp_home):
    """Same digest ingested twice produces the same --memories output (no duplicates)."""
    _memcap(["--transcript", str(FIXTURE)])
    digest = "package_manager | durable | prefers uv over pip\n\nHANDOFF: uv only."
    _memcap(["--ingest-digest", "--session-id", "s1", "--project", "p1"], input=digest)
    first = _memcap(["--memories"]).stdout
    _memcap(["--ingest-digest", "--session-id", "s1", "--project", "p1"], input=digest)
    second = _memcap(["--memories"]).stdout
    assert first.count("prefers uv over pip") == second.count("prefers uv over pip"), (
        "repeated ingest of identical digest produced duplicate memories"
    )


def test_inject_includes_active_patterns(tmp_home):
    """inject_context appends active co_edit and error_recurrence patterns from wiki."""
    wiki = tmp_home / ".claude" / "patterns" / "patterns"
    wiki.mkdir(parents=True)
    (wiki / "co-edit-a-b.md").write_text(
        "---\nkind: co_edit\nconfidence: 5\nstatus: active\n---\n\n# co-edit-a-b\n\nFiles a.py and b.py edited together (5 sessions).\n"
    )
    (wiki / "error-abc.md").write_text(
        "---\nkind: error_recurrence\nconfidence: 3\nstatus: active\n---\n\n# error-abc\n\nError recurs: ImportError (3 times).\n"
    )
    # stale pattern should be excluded
    (wiki / "stale-one.md").write_text("---\nkind: co_edit\nconfidence: 10\nstatus: stale\n---\n\n# stale-one\n\nShould not appear.\n")
    # project_streak should be excluded (not co_edit/error_recurrence)
    (wiki / "streak-proj.md").write_text(
        "---\nkind: project_streak\nconfidence: 7\nstatus: active\n---\n\n# streak-proj\n\nProject had 7 day streak.\n"
    )
    result = _memcap(["--inject"])
    assert "<patterns>" in result.stdout
    assert "a.py and b.py edited together" in result.stdout
    assert "ImportError" in result.stdout
    assert "Should not appear" not in result.stdout
    assert "7 day streak" not in result.stdout
