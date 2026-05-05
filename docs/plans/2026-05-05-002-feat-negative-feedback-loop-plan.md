---
title: "feat: Negative feedback loop for injected memories"
type: feat
status: active
date: 2026-05-05
---

# feat: Negative feedback loop for injected memories

## Overview

Today, claude-engram injects up to ~20 memories into every SessionStart and silently increments `exposure_count` for each one. There is no signal back into memory quality: a memory that consistently precedes user corrections is reinforced exactly as much as one that precedes a successful flow. This plan closes that loop. When a session shows correction signals (`detect_correction_heavy` or `detect_rapid_corrections`) shortly after memories are injected, those specific memories are attributed and **down-weighted** — never silently deleted in this iteration. Deletion is a deferred follow-up gated on operator review.

The feature is purely additive at the schema level (one new table) and reuses existing memdoctor signals. It does not change inject_context behavior, the SessionStart banner, or the executive cache.

---

## Problem Frame

- Injected memory mass grows monotonically: every SessionStart that touches a memory bumps `exposure_count`, which feeds the score and protects it from decay-eviction.
- The scoring formula (`exp_decay(...) + MIN(exposure_count/SAT, 1)`) treats reinforcement as unconditionally positive. Bad memories get the same boost as good ones.
- `memdoctor` already detects corrections per-session (`detect_correction_heavy`, `detect_rapid_corrections`, `detect_keep_going`) but never feeds those signals back into `memories`.
- No persistence of "which memories were active in which session" exists. Without that link, attribution is impossible.

The first-order missing term is the **edge from session → memory**. Add it, and the existing signals close the loop.

---

## Requirements Trace

- R1. Persist `(session_id, topic, injected_at)` for every memory that lands in an injected `<session-memory>` block.
- R2. Provide a memdoctor signal that, given a session flagged correction-heavy or rapid-corrections, emits the list of topics injected in that session and a per-topic confidence that they contributed.
- R3. Down-weight implicated memories by decrementing `exposure_count` (floor at 0). Never delete during this iteration.
- R4. Expose this through `engram doctor --negative` (rules-style output) and integrate the down-weight pass into the existing `engram doctor --propose` flow so it is opt-in, not silent-on-every-session.
- R5. Add a schema migration block (v3) for the new `injections` table; preserve the existing v2→v3 idempotency contract (`PRAGMA user_version`).
- R6. No regression on inject_context latency: the new INSERT happens once per SessionStart in the same transaction that already commits `last_accessed`/`exposure_count`.

---

## Scope Boundaries

- Not deleting memories automatically. Deletion remains a manual `engram forget` operation; this plan only down-weights.
- Not changing the inject scoring formula. Adjusting the `exp_decay` half-life or saturation is out of scope.
- Not back-filling historical attribution. The `injections` table starts empty at v3 migration; only sessions after the upgrade are attributable.
- Not adding a new top-level CLI command. Reuse `engram doctor` subcommands.
- Not changing F2 (snapshot enrichment). Planned separately.

### Deferred to Follow-Up Work

- Auto-delete on repeated negative attribution: requires operator confidence + UX for undo. Plan after F1 ships and we have real-world signal volume.
- Per-memory provenance UI in the patterns wiki.

---

## Context & Research

### Relevant Code and Patterns

- `tools/memcapture.py:471` — `inject_context()`. Already collects `kept_topics: list[str]` (line 530) before the existing `UPDATE memories SET last_accessed = ..., exposure_count = exposure_count + 1` block at line 569. The new INSERT belongs in the same transaction window, immediately before the commit on line 573.
- `tools/memcapture.py:228` — schema migration block. Pattern is `if version < N: ...; PRAGMA user_version = N`. Bump `LATEST_SCHEMA_VERSION` from 2 → 3.
- `tools/memcapture.py:191` — existing `memories` table; new `injections` sits next to it.
- `tools/memdoctor.py:159, 219` — `detect_correction_heavy`, `detect_rapid_corrections`. Both consume a `list[dict]` of session events and return a flag string. A new `detect_negative_attribution(events, conn)` follows the same shape but is db-aware.
- `tools/memdoctor.py:_analyze` — the aggregation entry point. Extending it requires threading the SQLite connection through, which it does not do today; the cleanest seam is to keep `_analyze` pure-on-events and add a new `_analyze_attribution(reports, conn)` post-pass.
- `tools/engram.py` doctor dispatch (~line 1155) — kwargs surface already accepts `propose`, `rules`, `per_project`, `json`. Add `negative: bool = False`.

### Institutional Learnings

- Pre-launch version discipline (memory): main-branch direct push is fine; no version bumps yet.
- Push workflow (memory): scout work pushes directly to main, no PR unless requested.
- Test subprocess audit (memory): tests invoke tools via `uv run` subprocess in addition to importing them. Any new behavior needs both shapes covered.

### External References

- None needed. Codebase already establishes every pattern this plan touches.

---

## Key Technical Decisions

- **Down-weight, do not delete (R3).** A bad memory should lose its reinforcement floor before it loses its existence. Decrement is reversible (a future correct-context use will reinforce it again). Delete is not.
- **Time-based attribution window, not prompt-count.** Existing memdoctor functions already operate on event timestamps and produce per-session signals. The simplest attribution is: if a session is flagged `correction-heavy` or `rapid-corrections`, every topic injected in that session is implicated. Refining (e.g., only corrections within 30min of inject) is a v2 concern.
- **Per-session bulk attribution, not per-prompt.** Granularity beyond session-level requires per-prompt instrumentation we do not currently have. Session-level is the right unit because injection is a session-level event.
- **Confidence = number of distinct sessions a topic was implicated in.** Single noisy session = confidence 1, low impact. Same topic implicated across 3+ sessions = strong signal. The `--propose` output ranks by this count.
- **Opt-in down-weight via `engram doctor --propose --negative`.** Silent down-weights on every doctor run risk eroding good memories from one bad session. Operator approval keeps the user in control pre-launch.
- **Confidence threshold for proposal: ≥ 2 distinct flagged sessions.** Single-session noise excluded by default. Configurable later.

---

## Open Questions

### Resolved During Planning

- *How do we track injected memories per session?* New `injections(session_id TEXT, topic TEXT, injected_at TEXT, PRIMARY KEY(session_id, topic))` table; insert at the same point `kept_topics` is committed.
- *What's the attribution window?* Session-level. Implicated = topic was injected into a session that later flagged correction-heavy or rapid-corrections.
- *Down-weight or delete?* Down-weight only this iteration (R3). Delete deferred.
- *Reuse memdoctor signals?* Yes. `detect_correction_heavy` + `detect_rapid_corrections` are sufficient. `detect_keep_going` and `detect_error_loop` are tool-failure / user-frustration signals not specific to memory quality, so excluded from the v1 attribution set.

### Deferred to Implementation

- Exact decrement amount (1? proportional to exposure?). Start with `-1 per implicated session`, floor 0, capped at current value. Tune after first real run.
- Whether to also bump `last_accessed` backwards (effectively age the memory). Skip in v1; decrement alone is the cleaner signal.

---

## Implementation Units

- U1. **Schema v3: add `injections` table**

**Goal:** Add `injections` table behind a v3 migration; bump `LATEST_SCHEMA_VERSION`.

**Requirements:** R1, R5

**Dependencies:** none

**Files:**
- Modify: `tools/memcapture.py` (schema block ~line 191; migration block ~line 228; constant `LATEST_SCHEMA_VERSION` ~line 121)
- Test: `tests/test_memcapture_schema.py` (existing) — extend with v3 assertions

**Approach:**
- Add `CREATE TABLE IF NOT EXISTS injections (session_id TEXT NOT NULL, topic TEXT NOT NULL, injected_at TEXT NOT NULL DEFAULT (datetime('now')), PRIMARY KEY (session_id, topic))` next to the existing `memories` block.
- New migration block: `if version < 3: self.conn.execute("CREATE TABLE IF NOT EXISTS injections ..."); PRAGMA user_version = 3`.
- Bump `LATEST_SCHEMA_VERSION = 3`.
- No index needed in v1 — table is append-only and queried by `session_id` lookups during `_analyze_attribution`. Reads remain O(rows-per-flagged-session), which is bounded (~20).

**Patterns to follow:**
- Existing v2 migration block at `tools/memcapture.py:228` — same shape, same idempotency contract.

**Test scenarios:**
- Happy path: a fresh in-memory DB at v0 migrates cleanly to v3 and `injections` exists.
- Edge case: a v2 DB (existing data, `PRAGMA user_version = 2`) migrates to v3 without altering `memories` rows.
- Edge case: re-running migration on a v3 DB is a no-op (idempotent).

**Verification:**
- `PRAGMA user_version` returns `3` after `MemoryDB()` init.
- `injections` table exists with the documented columns.

---

- U2. **Log injections in `inject_context`**

**Goal:** Persist the `(session_id, topic, injected_at)` rows for every memory rendered into the session-memory block.

**Requirements:** R1, R6

**Dependencies:** U1

**Files:**
- Modify: `tools/memcapture.py:471` (`inject_context`)
- Test: `tests/test_memcapture_inject.py` (existing or new)

**Approach:**
- `inject_context` already builds `kept_topics`. Get the active `session_id` from the same source `_on_session_start` already uses (env var `CLAUDE_SESSION_ID`, with a UUID fallback already present in `engram.py`).
- After the existing `UPDATE memories SET last_accessed = ..., exposure_count = exposure_count + 1 WHERE topic IN (...)` at line 569, add: `self.conn.executemany("INSERT OR IGNORE INTO injections (session_id, topic) VALUES (?, ?)", [(sid, t) for t in kept_topics])`.
- Single commit covers both writes (already commits at line 573).
- If `session_id` is unavailable (CLI-direct call to `inject_context`, e.g., the `_preview` path at line 1161), skip the INSERT silently. Don't synthesize an ID — that pollutes attribution data.

**Patterns to follow:**
- The existing `kept_topics` UPDATE block in `inject_context`.

**Test scenarios:**
- Happy path: calling `inject_context(project=...)` with a known session_id env var inserts one row per kept topic.
- Edge case: with `CLAUDE_SESSION_ID` unset, the INSERT is skipped and no exception is raised.
- Edge case: re-calling `inject_context` for the same session_id is idempotent (`INSERT OR IGNORE` on the composite PK).
- Edge case: when `kept_topics` is empty (fallback path), no INSERT is attempted.
- Integration: end-to-end via `subprocess.run(["uv", "run", str(ENGRAM), "_preview"])` — should not crash even though session_id is absent.

**Verification:**
- After a SessionStart that injects N topics, `SELECT COUNT(*) FROM injections WHERE session_id = ?` returns N.

---

- U3. **`detect_negative_attribution` + `_analyze_attribution`**

**Goal:** Given the existing per-session reports, produce a per-topic confidence count of negative attributions, joining `injections` with sessions flagged by `detect_correction_heavy` or `detect_rapid_corrections`.

**Requirements:** R2

**Dependencies:** U1, U2

**Files:**
- Modify: `tools/memdoctor.py` (new function near other `detect_*`; new `_analyze_attribution(reports, conn)` near `_analyze`)
- Test: `tests/test_memdoctor.py` (existing)

**Approach:**
- New `detect_negative_attribution(events: list[dict], session_id: str, conn) -> dict[str, int]`:
  - Returns `{}` unless `detect_correction_heavy(events) or detect_rapid_corrections(events)` flags.
  - When flagged, queries `SELECT topic FROM injections WHERE session_id = ?` and returns `{topic: 1 for topic in topics}`.
- New `_analyze_attribution(per_session_reports, conn) -> dict[str, int]`:
  - Iterates the per-session reports. For each flagged session, merges its negative-attribution dict into a project-wide accumulator (`Counter`-style sum).
  - Returns `{topic: total_implicated_session_count}`.
- Threshold the result at `MIN_NEGATIVE_SESSIONS = 2` when surfacing for `--propose --negative`. Below threshold, topic is included in `--negative` rules output but not in proposal.

**Patterns to follow:**
- Existing `detect_*` functions in `tools/memdoctor.py` (event-list-in, flag-out shape).
- Existing `_analyze` aggregation at `tools/memdoctor.py:_analyze`.

**Test scenarios:**
- Happy path: session flagged correction-heavy + injections rows for topics A,B,C → result `{A:1, B:1, C:1}`.
- Happy path: 3 flagged sessions sharing topic X → aggregate count `{X:3}`.
- Edge case: session not flagged → `detect_negative_attribution` returns `{}` even when injections exist.
- Edge case: session flagged but no injections rows (pre-v3 session, or skipped INSERT) → returns `{}`.
- Edge case: empty events list → returns `{}`.

**Verification:**
- `_analyze_attribution` returns a `dict[str, int]` and never raises on empty input or missing rows.

---

- U4. **CLI surfaces: `engram doctor --negative` and `--propose --negative`**

**Goal:** Wire the new analysis into the existing `engram doctor` surface; add a `--negative` flag that produces the attribution report, and extend `--propose` to honor it.

**Requirements:** R3, R4

**Dependencies:** U3

**Files:**
- Modify: `tools/memdoctor.py` (`run` kwargs; `_print_negative` printer; `propose_memories` to accept `apply_negative=False`)
- Modify: `tools/engram.py` doctor argparse subcommand + dispatch lambda (~line 1155)
- Test: `tests/test_memdoctor.py` (existing) — new `TestNegativeAttribution` class

**Approach:**
- `memdoctor.run` gains `negative: bool = False`. When set without `propose`, prints the `_analyze_attribution` results as a rules-style block (`topic | implicated_sessions`).
- When `--propose --negative` is passed, the proposal pass shows pending **down-weight** actions (`exposure_count -= 1`, floor 0) for topics meeting `>= MIN_NEGATIVE_SESSIONS` (default 2). Operator confirms via the same y/N prompt `propose_memories` already uses.
- `engram.py` `dr.set_defaults` lambda extended:
  ```python
  func=lambda a: memdoctor.run(
      project=a.project, rules=a.rules, per_project=a.per_project,
      propose=a.propose, json=a.json, negative=a.negative,
  )
  ```
- Argparse: add `dr.add_argument("--negative", action="store_true", help="show memories implicated in correction-heavy sessions")`.
- The actual UPDATE: `UPDATE memories SET exposure_count = MAX(0, exposure_count - 1) WHERE topic = ?` per approved topic.

**Patterns to follow:**
- Existing `--propose` flow in `tools/memdoctor.py`.
- Existing argparse `dr` subparser block in `tools/engram.py`.

**Test scenarios:**
- Happy path: `memdoctor.run(negative=True)` with an injections+flagged-session fixture prints implicated topics with counts.
- Happy path: `memdoctor.run(propose=True, negative=True)` decrements `exposure_count` for confirmed topics; floor honored.
- Edge case: `memdoctor.run(negative=True)` with empty `injections` table prints "no negative attributions".
- Edge case: `--propose --negative` skips topics below threshold.
- Integration (subprocess): `subprocess.run(["uv", "run", str(ENGRAM), "doctor", "--negative"])` exits 0 on a fresh DB.
- Integration (subprocess): `subprocess.run(["uv", "run", str(ENGRAM), "doctor", "--negative", "--json"])` emits a parseable JSON payload (extends existing `_json_payload`).

**Verification:**
- `engram doctor --negative` runs without exception on a v3 DB.
- A topic with implicated_sessions ≥ 2, after `--propose --negative` confirm-yes, has `exposure_count` reduced by exactly 1, never below 0.

---

## System-Wide Impact

- **Interaction graph:** SessionStart → `inject_context` (new INSERT). PreCompact and UserPromptSubmit hooks unchanged. `engram doctor` adds one subflag.
- **Error propagation:** All new writes are inside the existing `inject_context` transaction. If the INSERT fails (e.g., schema not yet at v3), the surrounding `last_accessed`/`exposure_count` UPDATE also fails — acceptable, because v3 migration runs on `MemoryDB.__init__` before `inject_context` is reachable.
- **State lifecycle risks:** None new. `injections` is append-only with a composite PK; no orphaned-state class. A future `engram forget --topic X` should also `DELETE FROM injections WHERE topic = X` for hygiene; track as a follow-up but do not block this plan.
- **API surface parity:** `memdoctor.run` is the single attribution surface; argparse and direct kwarg callers both go through it (post-namespace-fakery cleanup).
- **Integration coverage:** End-to-end `subprocess.run(["uv", "run", str(ENGRAM), "doctor", "--negative"])` proves the dispatch path. Per-function unit tests prove the scoring shape.
- **Unchanged invariants:** `inject_context` output format and char_budget unchanged. Memory scoring formula unchanged. Schema v2 reads unchanged.

---

## Risks & Dependencies

| Risk | Mitigation |
|------|------------|
| False positives — a single bad session implicates an actually-good memory. | Threshold ≥ 2 distinct flagged sessions before proposal; operator confirmation in `--propose`; decrement is reversible. |
| Migration race — first SessionStart after upgrade hits v3 init concurrently with another process. | Existing v2 migration is already exposed to this; no new contention. SQLite WAL + `IF NOT EXISTS` keep it safe. |
| `injections` table grows unbounded. | At ~20 rows per session, growth is slow. Add a `cleanup_ephemeral`-style daily prune for rows older than N days as a follow-up if it ever shows up in `engram doctor` reports. |
| Negative attribution is silently wrong because `detect_correction_heavy` itself is noisy. | Down-weight only, no delete. Operator-confirmed `--propose`. Telemetry comes from real-world use post-launch. |

---

## Documentation / Operational Notes

- README / handoff bullet should mention `engram doctor --negative` once the feature ships. Defer the doc update to the same commit that wires CLI surfaces (U4).
- After this plan ships, the `project_pending_work.md` memory should be updated with the F1 shipped marker and F2 status.

---

## Sources & References

- Origin scout report: `karpathy-scout-sebastianbreguel-claude-engram.md`
- Related code: `tools/memcapture.py` (schema, `inject_context`), `tools/memdoctor.py` (signals, `_analyze`), `tools/engram.py` (doctor dispatch)
- Pending-work memory: `project_pending_work.md`
