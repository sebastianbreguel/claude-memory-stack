"""Tests for U5: memdoctor structured signal codes.

Each detected signal name resolves to a {code, severity, safe_next_step, rule}
record via SIGNAL_INFO + signal_info(). JSON output exposes the structured
fields; human report prefixes signals with [severity:code]. RULES_MAP stays
backward-compatible for callers that just want the rule string.
"""

from __future__ import annotations

import io
import json
import sys
from contextlib import redirect_stdout
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "tools"))

from memdoctor import (  # noqa: E402
    CODE_CORRECTION_HEAVY,
    CODE_ERROR_LOOP,
    CODE_KEEP_GOING,
    CODE_RAPID_CORRECTIONS,
    CODE_RESTART_CLUSTER,
    RULES_MAP,
    SIGNAL_INFO,
    _json_payload,
    _print_summary,
    signal_info,
)


def test_signal_info_returns_full_record_for_known_name():
    info = signal_info("error-loop")
    assert info is not None
    assert info["code"] == CODE_ERROR_LOOP
    assert info["severity"] == "high"
    assert info["safe_next_step"]
    assert info["rule"]


def test_signal_info_returns_none_for_unknown():
    assert signal_info("not-a-real-signal") is None


def test_severity_heuristics_match_plan():
    assert SIGNAL_INFO["error-loop"]["severity"] == "high"
    assert SIGNAL_INFO["correction-heavy"]["severity"] == "high"
    assert SIGNAL_INFO["rapid-corrections"]["severity"] == "medium"
    assert SIGNAL_INFO["keep-going-loop"]["severity"] == "medium"
    assert SIGNAL_INFO["restart-cluster"]["severity"] == "low"


def test_codes_are_snake_case_constants():
    assert CODE_CORRECTION_HEAVY == "correction_heavy"
    assert CODE_ERROR_LOOP == "error_loop"
    assert CODE_KEEP_GOING == "keep_going"
    assert CODE_RAPID_CORRECTIONS == "rapid_corrections"
    assert CODE_RESTART_CLUSTER == "restart_cluster"


def test_rules_map_backward_compat_still_returns_strings():
    # Existing callers do `RULES_MAP[name]` and concat — that contract holds.
    for name in SIGNAL_INFO:
        assert isinstance(RULES_MAP[name], str)
        assert RULES_MAP[name] == SIGNAL_INFO[name]["rule"]


def test_json_payload_includes_structured_signals_list():
    report = {
        "sessions": 10,
        "totals": {"error-loop": 4, "correction-heavy": 2},
        "projects": {},
        "error_samples": [],
    }
    payload = _json_payload(report, want_rules=False)
    assert "signals" in payload
    by_name = {s["name"]: s for s in payload["signals"]}
    assert by_name["error-loop"]["code"] == CODE_ERROR_LOOP
    assert by_name["error-loop"]["severity"] == "high"
    assert by_name["error-loop"]["count"] == 4
    assert by_name["error-loop"]["safe_next_step"]
    # Existing keys still present (regression guard).
    assert payload["totals"] == {"error-loop": 4, "correction-heavy": 2}
    assert "projects" in payload
    assert "error_samples" in payload


def test_json_payload_signals_sorted_by_count_desc():
    report = {
        "sessions": 5,
        "totals": {"error-loop": 1, "correction-heavy": 3, "keep-going-loop": 2},
        "projects": {},
        "error_samples": [],
    }
    payload = _json_payload(report, want_rules=False)
    counts = [s["count"] for s in payload["signals"]]
    assert counts == sorted(counts, reverse=True)


def test_json_payload_skips_unknown_signals():
    report = {
        "sessions": 5,
        "totals": {"error-loop": 2, "ghost-signal": 1},
        "projects": {},
        "error_samples": [],
    }
    payload = _json_payload(report, want_rules=False)
    names = [s["name"] for s in payload["signals"]]
    assert "ghost-signal" not in names
    assert "error-loop" in names


def test_json_payload_empty_totals_yields_empty_signals_list():
    report = {"sessions": 0, "totals": {}, "projects": {}, "error_samples": []}
    payload = _json_payload(report, want_rules=False)
    assert payload["signals"] == []


def test_json_payload_round_trip_serializable():
    report = {
        "sessions": 1,
        "totals": {"correction-heavy": 1},
        "projects": {},
        "error_samples": [],
    }
    payload = _json_payload(report, want_rules=False)
    # Must be JSON-serializable.
    json.dumps(payload)


def test_print_summary_prefixes_severity_and_code():
    report = {
        "sessions": 4,
        "totals": {"error-loop": 3},
        "projects": {},
        "error_samples": [],
    }
    buf = io.StringIO()
    with redirect_stdout(buf):
        _print_summary(report)
    out = buf.getvalue()
    assert "[high:error_loop]" in out
    assert "error-loop: 3" in out


def test_print_summary_omits_prefix_for_unknown_signal():
    report = {
        "sessions": 2,
        "totals": {"unknown-signal": 1},
        "projects": {},
        "error_samples": [],
    }
    buf = io.StringIO()
    with redirect_stdout(buf):
        _print_summary(report)
    out = buf.getvalue()
    assert "unknown-signal: 1" in out
    # No prefix bracket when the signal isn't in SIGNAL_INFO.
    assert "[high:unknown" not in out
    assert "[medium:unknown" not in out
    assert "[low:unknown" not in out
