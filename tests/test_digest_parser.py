"""Tests for parse_digest_output covering legacy 3-field and extended 6-field forms.

U2: DIGEST_PROMPT now allows optional why/where/learned fields. Parser must
tolerate both shapes without breaking existing call sites.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "tools"))

from memcapture import parse_digest_output  # noqa: E402


def _facts_only(result):
    return [m for m in result if not m["topic"].startswith("handoff_")]


def test_legacy_3_field_still_parses():
    text = "package_manager | durable | prefers uv over pip\n"
    out = _facts_only(parse_digest_output(text))
    assert len(out) == 1
    m = out[0]
    assert m["topic"] == "package_manager"
    assert m["durability"] == "durable"
    assert m["content"] == "prefers uv over pip"
    assert m["why"] is None
    assert m["where_ctx"] is None
    assert m["learned"] is None


def test_extended_6_field_populates_optional_fields():
    text = "package_manager | durable | prefers uv | speed and lockfile semantics | python projects | use uv add not pip install\n"
    out = _facts_only(parse_digest_output(text))
    assert len(out) == 1
    m = out[0]
    assert m["topic"] == "package_manager"
    assert m["content"] == "prefers uv"
    assert m["why"] == "speed and lockfile semantics"
    assert m["where_ctx"] == "python projects"
    assert m["learned"] == "use uv add not pip install"


def test_extended_dash_normalizes_to_none():
    text = "x | durable | y | - | - | -\n"
    out = _facts_only(parse_digest_output(text))
    assert len(out) == 1
    m = out[0]
    assert m["why"] is None
    assert m["where_ctx"] is None
    assert m["learned"] is None


def test_extended_partial_optional_fields():
    text = "x | durable | y |   | repo-x | -\n"
    out = _facts_only(parse_digest_output(text))
    assert len(out) == 1
    m = out[0]
    assert m["why"] is None
    assert m["where_ctx"] == "repo-x"
    assert m["learned"] is None


def test_invalid_arity_skipped():
    # 4 and 5-field rows are malformed — should be skipped silently
    text = "a | durable | b | c\nx | durable | y | z | w\nok | durable | content\n"
    out = _facts_only(parse_digest_output(text))
    assert len(out) == 1
    assert out[0]["topic"] == "ok"


def test_invalid_durability_in_extended_skipped():
    text = "x | bogus | y | - | - | -\n"
    out = _facts_only(parse_digest_output(text))
    assert out == []


def test_mixed_legacy_and_extended_in_one_batch():
    text = (
        "test_style | durable | use pytest fixtures\n"
        "current_refactor | ephemeral | wiring schema v4 | drop UNIQUE on topic | claude-engram | rebuild table per recipe\n"
    )
    out = _facts_only(parse_digest_output(text))
    assert len(out) == 2
    by_topic = {m["topic"]: m for m in out}
    assert by_topic["test_style"]["why"] is None
    assert by_topic["current_refactor"]["why"] == "drop UNIQUE on topic"
    assert by_topic["current_refactor"]["where_ctx"] == "claude-engram"
    assert by_topic["current_refactor"]["learned"] == "rebuild table per recipe"
