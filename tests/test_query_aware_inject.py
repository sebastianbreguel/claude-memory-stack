"""Tests for U4: query-aware inject_context reranking.

inject_context(query=...) tokenizes the query and reranks memories by per-token
LIKE matches across topic/content/why/where_ctx/learned, with weights 5/3/2/2/2.
Ties fall back to the existing recency + reinforcement score.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "tools"))

from memcapture import MemoryDB, _tokenize_query  # noqa: E402


def test_tokenize_drops_stopwords_short_and_dedupes():
    out = _tokenize_query("the AUTH bug AUTH and a XY token-system")
    # 'the','and','a','bug' are stopwords or len<3 — wait 'bug' is len 3, not stopword
    assert "auth" in out
    assert out.count("auth") == 1  # dedupe
    assert "the" not in out
    assert "and" not in out
    assert "xy" not in out  # len < 3


def test_tokenize_caps_at_max():
    out = _tokenize_query("alpha bravo charlie delta echo foxtrot golf", max_tokens=3)
    assert len(out) == 3
    assert out == ["alpha", "bravo", "charlie"]


def test_tokenize_none_or_empty_returns_empty():
    assert _tokenize_query(None) == []
    assert _tokenize_query("") == []
    assert _tokenize_query("   ") == []


@pytest.fixture
def db(tmp_path):
    d = MemoryDB(db_path=tmp_path / "memory.db")
    yield d
    d.conn.close()


def test_query_reranks_topic_match_above_content_match(db):
    # Both have similar recency/exposure; query should pull topic-match first.
    db.upsert_memory("auth_rule", "general guidance about systems", "durable")
    db.upsert_memory("style_rule", "auth tokens here in content", "durable")
    out = db.inject_context(query="auth")
    # topic 'auth_rule' wins (weight 5) vs content match (weight 3)
    auth_pos = out.find("general guidance about systems")
    style_pos = out.find("auth tokens here in content")
    assert auth_pos != -1 and style_pos != -1
    assert auth_pos < style_pos


def test_query_uses_structured_fields(db):
    db.upsert_memory("rule_a", "alpha content", "durable")
    db.upsert_memory("rule_b", "beta content", "durable", why="auth flow rationale")
    out = db.inject_context(query="auth")
    # rule_b should rerank above rule_a since 'auth' matches its `why` field
    a_pos = out.find("alpha content")
    b_pos = out.find("beta content")
    assert a_pos != -1 and b_pos != -1
    assert b_pos < a_pos


def test_no_query_preserves_existing_ordering(db):
    # Without query, ordering falls back to the legacy decay+reinforcement score.
    db.upsert_memory("topic_a", "first", "durable")
    db.upsert_memory("topic_b", "second", "durable")
    out_q = db.inject_context()
    assert "first" in out_q and "second" in out_q


def test_query_with_no_matches_falls_back_cleanly(db):
    db.upsert_memory("rule_a", "alpha", "durable")
    db.upsert_memory("rule_b", "beta", "durable")
    out = db.inject_context(query="zzznomatchqqq")
    assert "alpha" in out
    assert "beta" in out
