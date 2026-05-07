#!/usr/bin/env python3
"""eval_warmstart — measure how often users re-state context the inject already had.

For each captured session, simulate the SessionStart inject as it would have
fired at T=0, then scan the first N user messages for re-statement of injected
content. Re-statement rate is the % of sessions where any of the first N user
messages overlaps the inject above a token-overlap threshold.

Lower rate = inject is doing its job (user trusts the injected context).
Higher rate = user is re-explaining things engram already knew → memory quality
or inject ranking is leaking signal.

Usage:
    uv run tools/eval_warmstart.py run [--n 20] [--threshold 0.30] [--first 3]
    uv run tools/eval_warmstart.py dump [--n 20] [--out eval/warmstart_<date>.md]
"""
# /// script
# requires-python = ">=3.12"
# dependencies = []
# ///

from __future__ import annotations

import argparse
import datetime as _dt
import json
import random
import re
import sqlite3
import sys
from pathlib import Path

REPO_TOOLS = Path(__file__).resolve().parent
if str(REPO_TOOLS) not in sys.path:
    sys.path.insert(0, str(REPO_TOOLS))

import memcapture  # noqa: E402

DB_PATH = Path.home() / ".claude" / "memory.db"
DEFAULT_N = 20
DEFAULT_FIRST = 3
DEFAULT_THRESHOLD = 0.30
DEFAULT_OUT_DIR = Path("eval")

_TOKEN_RE = re.compile(r"[a-z0-9_]{3,}")
_STOPWORDS = frozenset(
    """the and for with from this that have what when where will you are can was its
    not but our your they them then than into onto over under been being has had
    just now also see use using used uses make made get got let know like need needs""".split()
)


def _tokens(text: str) -> set[str]:
    """Lowercase alphanumeric tokens (≥3 chars), stopwords removed."""
    return {t for t in _TOKEN_RE.findall(text.lower()) if t not in _STOPWORDS}


def _extract_user_text(obj: dict) -> str:
    """Pull plain text from a JSONL user message; mirrors memcapture handling."""
    msg = obj.get("message", {})
    content = msg.get("content", "")
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text":
                parts.append(block.get("text", ""))
        text = "\n".join(parts)
    elif isinstance(content, str):
        text = content
    else:
        text = ""
    text = re.sub(r"<system-reminder>.*?</system-reminder>", "", text, flags=re.DOTALL)
    text = re.sub(r"<[^>]+>.*?</[^>]+>", "", text, flags=re.DOTALL)
    return text.strip()


def _first_user_messages(transcript: Path, n: int) -> list[str]:
    """First `n` real user messages (skips system reminders, slash commands, tool_results)."""
    out: list[str] = []
    if not transcript.exists():
        return out
    for line in transcript.read_text(encoding="utf-8", errors="replace").splitlines():
        if not line.strip():
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        if obj.get("type") != "user":
            continue
        text = _extract_user_text(obj)
        if not text or len(text) < 10:
            continue
        if text.startswith("<local-command") or text.startswith("<command-name>"):
            continue
        out.append(text)
        if len(out) >= n:
            break
    return out


def _overlap_ratio(user_tokens: set[str], inject_tokens: set[str]) -> float:
    """Fraction of user tokens that also appear in the inject."""
    if not user_tokens:
        return 0.0
    return len(user_tokens & inject_tokens) / len(user_tokens)


def _candidate_sessions(db_path: Path, n: int, seed: int | None = None) -> list[dict]:
    """Sample `n` sessions that have a real transcript and ≥1 prior memory for the project."""
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        """
        SELECT s.session_id, s.project, s.transcript_path, s.message_count, s.captured_at
        FROM sessions s
        WHERE s.transcript_path IS NOT NULL
          AND s.project IS NOT NULL
          AND s.message_count >= 3
          AND EXISTS (
              SELECT 1 FROM memories m
              LEFT JOIN sessions s2 ON m.source_session = s2.session_id
              WHERE m.superseded_by IS NULL
                AND m.created_at < s.captured_at
                AND (m.durability = 'durable' OR s2.project = s.project)
          )
        ORDER BY RANDOM()
        LIMIT ?
        """,
        (n * 4,),  # over-sample; transcript may be missing on disk
    ).fetchall()
    conn.close()

    if seed is not None:
        random.seed(seed)
        rows = list(rows)
        random.shuffle(rows)

    out: list[dict] = []
    for row in rows:
        if Path(row["transcript_path"]).exists():
            out.append(dict(row))
            if len(out) >= n:
                break
    return out


def _evaluate_session(session: dict, db: memcapture.MemoryDB, first: int, threshold: float) -> dict:
    """Simulate inject + scan first `first` user messages for re-statement.

    Uses session.captured_at as historical cutoff so the simulated inject only
    sees memories that existed before this session was captured. Approximation —
    captured_at is post-session, but strictly closer to T=0 than current state.
    """
    inject_text = db.inject_context(
        project=session["project"],
        cutoff_ts=session.get("captured_at"),
    ).strip()
    inject_tokens = _tokens(inject_text)
    user_msgs = _first_user_messages(Path(session["transcript_path"]), first)

    per_msg = []
    max_ratio = 0.0
    for msg in user_msgs:
        ratio = _overlap_ratio(_tokens(msg), inject_tokens)
        per_msg.append((msg[:200], ratio))
        max_ratio = max(max_ratio, ratio)

    return {
        "session_id": session["session_id"],
        "project": session["project"],
        "inject_chars": len(inject_text),
        "user_msg_count": len(user_msgs),
        "max_overlap": max_ratio,
        "restated": max_ratio >= threshold,
        "per_msg": per_msg,
        "inject_text": inject_text,
    }


def cmd_run(args: argparse.Namespace) -> int:
    sessions = _candidate_sessions(args.db_path, args.n, args.seed)
    if not sessions:
        print("No eligible sessions (need transcript + prior memories for project).")
        return 1

    db = memcapture.MemoryDB()
    try:
        results = [_evaluate_session(s, db, args.first, args.threshold) for s in sessions]
    finally:
        db.close()

    restated = sum(1 for r in results if r["restated"])
    rate = restated / len(results)
    avg_overlap = sum(r["max_overlap"] for r in results) / len(results)

    print(f"sessions={len(results)}  threshold={args.threshold:.2f}  first={args.first}")
    print(f"re-statement rate = {rate:.1%}  ({restated}/{len(results)})")
    print(f"avg max-overlap   = {avg_overlap:.3f}")
    print()
    print("worst offenders (top overlap):")
    for r in sorted(results, key=lambda x: x["max_overlap"], reverse=True)[:5]:
        print(f"  {r['max_overlap']:.2f}  {r['project'][:40]:<40} {r['session_id'][:8]}")
    return 0


def cmd_dump(args: argparse.Namespace) -> int:
    sessions = _candidate_sessions(args.db_path, args.n, args.seed)
    if not sessions:
        print("No eligible sessions.")
        return 1

    db = memcapture.MemoryDB()
    try:
        results = [_evaluate_session(s, db, args.first, args.threshold) for s in sessions]
    finally:
        db.close()

    out = args.out
    out.parent.mkdir(parents=True, exist_ok=True)

    restated = sum(1 for r in results if r["restated"])
    rate = restated / len(results) if results else 0.0
    lines = [
        f"# warmstart eval — {_dt.date.today().isoformat()}",
        "",
        f"sessions={len(results)}  threshold={args.threshold:.2f}  first={args.first}",
        f"re-statement rate = {rate:.1%}  ({restated}/{len(results)})",
        "",
        "---",
        "",
    ]
    for i, r in enumerate(results, 1):
        flag = "RESTATED" if r["restated"] else "ok"
        lines.append(f"## [{i}] {flag}  overlap={r['max_overlap']:.2f}  {r['project']}")
        lines.append(f"session: `{r['session_id']}`")
        lines.append("")
        lines.append("**Inject (T=0 simulation):**")
        lines.append("```")
        lines.append(r["inject_text"][:1500] or "(empty)")
        lines.append("```")
        lines.append("")
        lines.append("**First user messages:**")
        for j, (msg, ratio) in enumerate(r["per_msg"], 1):
            lines.append(f"- [{j}] overlap={ratio:.2f}: `{msg}`")
        lines.append("")
        lines.append("---")
        lines.append("")
    out.write_text("\n".join(lines))
    print(f"Wrote {len(results)} sessions to {out}  (rate={rate:.1%})")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="eval_warmstart — re-statement rate eval")
    sub = parser.add_subparsers(dest="cmd", required=True)

    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--n", type=int, default=DEFAULT_N, help="sessions to sample")
    common.add_argument("--first", type=int, default=DEFAULT_FIRST, help="first N user msgs to scan")
    common.add_argument("--threshold", type=float, default=DEFAULT_THRESHOLD, help="overlap ratio to flag re-statement")
    common.add_argument("--db-path", type=Path, default=DB_PATH)
    common.add_argument("--seed", type=int, default=None)

    pr = sub.add_parser("run", parents=[common], help="run eval, print aggregate")
    pr.set_defaults(func=cmd_run)

    pd = sub.add_parser("dump", parents=[common], help="write per-session breakdown to markdown")
    default_out = DEFAULT_OUT_DIR / f"warmstart_{_dt.date.today().isoformat()}.md"
    pd.add_argument("--out", type=Path, default=default_out)
    pd.set_defaults(func=cmd_dump)

    return parser


def main() -> int:
    args = build_parser().parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
