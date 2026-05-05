---
title: "feat: memory-quality bundle — schema v4, supersede, query-aware retrieval, structured codes"
type: feat
status: active
date: 2026-05-05
---

# Memory-Quality Bundle

## Overview

Adopt the panel-approved memory-quality wins from the Gentleman/engram comparison. The audit confirmed `DIGEST_PROMPT` extracts free-text `topic | durability | content` with only light filtering ("skip routine actions"), so the bottleneck is **write-time signal density** + **DB-side conflict resolution** + **query-aware retrieval** — not just exposure ranking. This bundle ships the smallest set of feature changes that move precision without paying the cost of a second LLM pass (`mem_judge`) or embeddings.

Six implementation units, each independently shippable. No second LLM gate. Backward-compatible across DIGEST_PROMPT and inject_context.

---

## Problem Frame

After F1 (negative-feedback loop) + F2 (snapshot enrichment), the remaining memory-quality gaps are:

1. **Memories are unstructured free text.** A topic + content pair carries no `why` (rationale), no `where` (cwd/repo scope), no `learned` (reflection). When F1 decrements a topic for being implicated in corrections, it cannot tell *why* the memory misfired or whether it applied to *this* project.
2. **Dedupe is LLM-side, not DB-side.** `DIGEST_PROMPT` asks the LLM to "reuse existing topics" but enforcement is an upsert that overwrites silently. Contradictions are never surfaced; old contents are lost without a supersede chain.
3. **`inject_context` ignores available query signal.** F2 already builds a header with `branch / dirty_files / recent_commits / last_error`. Yet `inject_context` ranks memories by exposure_count + recency only — no FTS5 BM25 against the query context.
4. **memdoctor signals are free-text bullets.** F1's decrement weight is binary (flagged or not). Severity / `safe_next_step` are not structured, so F1 cannot weight decay by signal severity.

The panel's verdict (3 lenses) converges on these four: structured fields stripped to what earns weight, DB-side supersede, query-aware retrieval, structured signal codes. The panel kills `mem_judge` (cost) and `session_summary` (executive cache duplicate) and defers embeddings retrieval.

---

## Requirements Trace

- R1. `memories` table carries optional `why`, `where_ctx`, `learned` text fields and a `superseded_by` FK for conflict chains. Schema v4 migration is idempotent and additive.
- R2. `DIGEST_PROMPT` accepts the new optional fields without breaking on 3-field legacy lines. Parser tolerates both 3-field and 6-field forms.
- R3. `upsert_memory` detects content drift on the same topic and creates a supersede chain instead of silent overwrite. Old row gets `superseded_by = new_row_id`; current SELECT excludes superseded rows by default.
- R4. `inject_context` reranks memories with FTS5 BM25 when a query string is available (F2 header). Falls back to current exposure+recency when no query.
- R5. memdoctor signal records expose `{code, severity, safe_next_step}` keys in JSON output and report. F1's `_apply_negative_downweight` weights the decrement by severity (1 for low, 2 for high).
- R6. Backward compat: existing memory.db files migrate cleanly to v4, existing JSON `engram doctor` output adds new keys without removing old ones.

---

## Scope Boundaries

- **No `mem_judge` write gate.** Adding a second LLM pass on every PreCompact doubles cost for marginal precision; panel killed it.
- **No embeddings.** Retrieval stays SQLite + FTS5; embeddings would require new dep + eval harness.
- **No per-session summary memory.** `engram/executive/<cwd-slug>.md` already covers it.
- **No structured-codes-as-DB-rows in `memories`.** Codes belong to memdoctor signals, not memory rows.
- **No DIGEST_PROMPT semantic-quality gate.** Hardening the prompt is a follow-up; this plan only widens its output schema.

### Deferred to Follow-Up Work

- Harden `DIGEST_PROMPT` with explicit discard criteria (low signal, duplicate-of-existing) — separate plan if eval data shows precision still leaks.
- Cluster F1 decrements by `why` pattern in memdoctor — depends on accumulating `why`-tagged memories first; revisit after launch.
- BM25 weight tuning for `inject_context` — initial weights are heuristic; tune from `eval_corrections.py` precision.

---

## Context & Research

### Relevant Code and Patterns

- `tools/memcapture.py` — `MemoryDB._migrate` (schema v3 block at `if version < 3`); `MemoryDB.LATEST_SCHEMA_VERSION` ClassVar; `MemoryDB.upsert_memory`; `MemoryDB.inject_context`; `parse_digest_output`
- `tools/engram.py` — `DIGEST_PROMPT` (lines 222–237); `_git_state` returning header inputs; `_run_llm` snapshot branch composing the F2 header
- `tools/memdoctor.py` — `detect_*` signal functions; `_print_*` formatters; `run()` JSON branch; `MIN_NEGATIVE_SESSIONS`; `_apply_negative_downweight`
- F1 origin: `docs/plans/2026-05-05-002-feat-negative-feedback-loop-plan.md`
- F2 origin: `docs/plans/2026-05-05-003-feat-snapshot-enrichment-plan.md`

### Institutional Learnings

- Schema migrations bump `LATEST_SCHEMA_VERSION` ClassVar + add `if version < N:` block (project CLAUDE.md). Use `CREATE TABLE IF NOT EXISTS` and `ALTER TABLE … ADD COLUMN` for idempotency.
- FTS5 already indexed on `content` — reuse for BM25 ranking term, no new vtable needed.
- Snapshot LLM contract is JSON; never modify SNAPSHOT_PROMPT itself (per memory `feedback_snapshot_enrichment`). DIGEST_PROMPT is plain-line format — safe to extend with optional fields.
- F1 ships in same commit as injections table — composite PK + INSERT OR IGNORE for idempotency.

### External References

- Panel verdict: 3 lenses on Gentleman/engram features → consensus + tension analysis applied. See conversation context.

---

## Key Technical Decisions

- **`why` instead of full What/Why/Where/Learned**: structured fields earn weight only when retrieval or F1 use them. `why` informs F1 clustering; `where_ctx` enables cwd filtering; `learned` is reflection that the LLM can populate but no consumer reads yet (forward-compat — kept nullable). "What" duplicates `topic`+`content` — drop. (Simplificación lens, partial Arquitectura.)
- **Supersede via `superseded_by` FK, not delete**: preserves audit trail and lets memdoctor reconstruct decision history. Current SELECT filters `WHERE superseded_by IS NULL`.
- **Content-drift detection via simple text inequality**: when `upsert_memory` finds an existing row with same topic but `content` differs (after whitespace normalization), it inserts new + supersedes old. Embeddings are out of scope; pure-text mismatch is good enough until eval data says otherwise.
- **Query-aware ranking is additive, not replacement**: BM25 score adds as third term to existing exposure+recency formula, not replaces it. Falls back to legacy ordering when no query.
- **memdoctor signal codes are constants, not enums**: keep signals as plain dicts with `code: str`, `severity: Literal["low", "medium", "high"]`, `safe_next_step: str`. No new types module — codes live as module-level string constants in `memdoctor.py`.
- **F1 severity weighting is multiplicative, not threshold-shifting**: `decrement = 1 * severity_weight` where weight ∈ {1, 2, 3}. Threshold (`MIN_NEGATIVE_SESSIONS = 2`) unchanged.

---

## Open Questions

### Resolved During Planning

- *Should we add `mem_judge` gate?* — No. Panel consensus: doubles LLM cost on PreCompact for marginal precision. Defer until eval data justifies.
- *Should structured fields be required or optional?* — Optional (NULL allowed). DIGEST_PROMPT can emit 3-field or 6-field lines; parser handles both.
- *Should supersede chain be exposed in `inject_context`?* — No. inject_context filters `WHERE superseded_by IS NULL`; only memdoctor / debug paths see history.

### Deferred to Implementation

- Exact BM25 weight relative to exposure+recency — start at 0.4 BM25 / 0.4 exposure / 0.2 recency, tune from eval.
- Whitespace-normalization function for content-drift detection — likely `re.sub(r"\s+", " ", text).strip()`, decide at impl.
- Should `_apply_negative_downweight` skip low-severity signals entirely, or just weight=0.5? — start with weight, decide if too noisy.

---

## Implementation Units

- U1. **Schema v4 migration: structured memory fields + supersede FK**

**Goal:** Add `why`, `where_ctx`, `learned` (TEXT NULL) and `superseded_by` (INTEGER NULL, FK to `memories.id`) to `memories` table. Bump `LATEST_SCHEMA_VERSION` to 4. Migration idempotent + additive.

**Requirements:** R1, R6

**Dependencies:** None

**Files:**
- Modify: `tools/memcapture.py` (`MemoryDB._migrate`, `MemoryDB.LATEST_SCHEMA_VERSION`, `_create_tables` SQL block)
- Test: `tests/test_e2e.py` (rename `test_schema_user_version_is_3` → `_4`, assert new columns)
- Test: `tests/test_memcapture.py` (new test for migration v3 → v4)

**Approach:**
- Add `if version < 4:` block to `_migrate` running `ALTER TABLE memories ADD COLUMN why TEXT`, etc., then `PRAGMA user_version = 4`.
- Update `_create_tables` `memories` DDL to include all four new columns (so fresh DBs match migrated DBs).
- New rows default to NULL; existing rows untouched (NULL-fill is implicit via ADD COLUMN).
- No index on new columns yet — wait for eval data showing where_ctx filtering hits a hot path.

**Patterns to follow:**
- v3 migration block (injections table) — same `if version < N:` shape, idempotent.

**Test scenarios:**
- Happy path: fresh `MemoryDB(db_path=…)` → `PRAGMA user_version` returns 4, `PRAGMA table_info(memories)` includes `why`, `where_ctx`, `learned`, `superseded_by`.
- Edge case: pre-existing v3 DB on disk → opening triggers migration to v4 without data loss; existing rows have NULL for new columns.
- Edge case: re-opening v4 DB → no-op migration, version stays 4, no SQL errors.

**Verification:** Both fresh and migrated DBs report `user_version = 4` and expose the four new columns. Existing memory rows survive migration with NULL on new fields.

---

- U2. **Extend DIGEST_PROMPT + parse_digest_output for 6-field form**

**Goal:** Allow LLM to emit `topic | durability | content | why | where | learned` (last 3 optional, "-" or empty = NULL). Parser tolerates 3-field legacy and 6-field new form.

**Requirements:** R2, R6

**Dependencies:** U1

**Files:**
- Modify: `tools/engram.py` (`DIGEST_PROMPT` text, lines 222–237)
- Modify: `tools/memcapture.py` (`parse_digest_output`, `_parse_fact_line` helper)
- Test: `tests/test_memcapture.py` (extend digest-parser tests)

**Approach:**
- Update `DIGEST_PROMPT` to describe 6-field optional form: "Optionally append ` | why | where | learned` to a fact when meaningful. Use `-` for any field you cannot fill. Legacy 3-field lines remain valid."
- `_parse_fact_line` accepts `len(parts) in (3, 6)`: 3-field path unchanged; 6-field path validates durability + maps `"-"` / `""` → None for the trailing fields. Returns `(topic, durability, content, why, where_ctx, learned)` tuple (or None).
- `parse_digest_output` propagates new fields into the memory dict: `{"topic", "content", "durability", "why": str | None, "where_ctx": str | None, "learned": str | None}`.

**Patterns to follow:**
- Existing `_parse_fact_line` tuple-return + None-on-invalid pattern.

**Test scenarios:**
- Happy path (legacy): `"package_manager | durable | prefers uv"` → memory dict with `why=None, where_ctx=None, learned=None`.
- Happy path (new): `"package_manager | durable | prefers uv | speed + lockfile | python projects | use uv add not pip"` → all six fields populated.
- Edge case: `"x | durable | y | - | - | -"` → trailing 3 normalized to None.
- Edge case: 4-field or 5-field input → parser returns None (treated as malformed, skipped).
- Edge case: empty `why` field with non-empty `where` (e.g., `"x | durable | y |  | repo-x | -"`) → `why=None, where_ctx="repo-x", learned=None`.
- Error path: 6-field with invalid durability → None.

**Verification:** Parser produces both legacy (3 keys) and extended (6 keys) memory dicts correctly. No regressions on existing digest fixtures.

---

- U3. **DB-side supersede on `upsert_memory` content drift**

**Goal:** When `upsert_memory` is called for an existing topic and `content` differs (after whitespace normalization), insert a new row and set `superseded_by = new_row_id` on the old row. Current reads filter `WHERE superseded_by IS NULL`.

**Requirements:** R3, R6

**Dependencies:** U1, U2

**Files:**
- Modify: `tools/memcapture.py` (`MemoryDB.upsert_memory`, `MemoryDB.inject_context` SELECT clause, any other `SELECT … FROM memories` paths)
- Test: `tests/test_memcapture.py` (new tests for supersede chain)

**Approach:**
- New helper `_normalize_text(s: str) -> str`: collapse whitespace, strip.
- `upsert_memory(topic, content, durability, ...)`:
  - SELECT existing row by topic where `superseded_by IS NULL`.
  - If none → INSERT (current behavior).
  - If exists and `_normalize_text(old.content) == _normalize_text(content)` → UPDATE in place (current behavior, just touches `last_seen_at` / exposure).
  - If exists and content differs → INSERT new row with the new content + new structured fields, then UPDATE old row's `superseded_by = new.id`. Single transaction.
- All SELECTs that surface "current" memories add `AND superseded_by IS NULL` (inject_context, list, etc.). Audit/debug paths can opt out.

**Patterns to follow:**
- F1 commit `81d7c2e` — multi-statement single-transaction upsert pattern.

**Test scenarios:**
- Happy path: same topic + same content twice → 1 row, exposure_count incremented, no supersede.
- Happy path: same topic + drifted content → 2 rows, old has `superseded_by = new.id`, current SELECT returns only new.
- Edge case: whitespace-only diff → treated as same content (no supersede chain).
- Edge case: 3-deep supersede chain (A → B → C) → only C visible in current SELECT; A.superseded_by = B.id, B.superseded_by = C.id.
- Integration: F1 `inject_context` followed by content-drift upsert → injections table still references old topic name (foreign-key-free by design); F1 attribution path unaffected.

**Verification:** Drifted content creates supersede chain instead of silent overwrite. Current memory selection (inject_context, list) shows only un-superseded rows. F1 negative-feedback loop continues to work on current rows.

---

- U4. **Query-aware FTS5 BM25 reranking in `inject_context`**

**Goal:** When a query string is available (from F2 header context — branch + last_error + recent_commits), add BM25 score as third term in memory selection ranking.

**Requirements:** R4

**Dependencies:** U1 (no hard requirement; works on v3, but ships in v4 bundle)

**Files:**
- Modify: `tools/memcapture.py` (`MemoryDB.inject_context` signature + ranking SQL)
- Modify: `tools/engram.py` (caller sites in `_on_session_start` and `_on_user_prompt`, pass query string built from F2 inputs)
- Test: `tests/test_memcapture.py` (new tests for query-aware ranking)

**Approach:**
- `inject_context(session_id=None, query: str | None = None, ...)`. Default None → existing behavior unchanged.
- When `query` is set: SQL becomes `SELECT m.*, bm25(memories_fts) AS bm25_score FROM memories m JOIN memories_fts ON memories_fts.rowid = m.id WHERE memories_fts MATCH ? AND m.superseded_by IS NULL`, then `ORDER BY (0.4 * normalized_bm25 + 0.4 * normalized_exposure + 0.2 * recency_term) DESC LIMIT N`.
- Normalization: divide each term by max within the result set so they're 0..1.
- When FTS5 returns < N results for the query, fall back to legacy ranking for the gap (UNION strategy or two-step).
- Caller in `_on_session_start`: build query from `f"{branch} {last_error or ''} {' '.join(recent_commits)}"` already computed for F2 header.

**Patterns to follow:**
- F2 `_git_state` outputs already constructed in `_run_llm` snapshot branch — reuse upstream.
- Existing FTS5 indexing on `content` (no schema change needed for BM25).

**Test scenarios:**
- Happy path: 5 memories (A, B, C, D, E), query matches B+D content → B+D rank above A/C/E even with lower exposure_count.
- Happy path: query=None → ranking identical to pre-U4 behavior (regression guard).
- Edge case: query MATCHes 0 memories → falls back fully to legacy ranking.
- Edge case: query MATCHes 2 memories, N=5 → top 2 are FTS-ranked, slots 3–5 filled by legacy ranking.
- Edge case: query string contains FTS5 special chars (e.g., `last_error` with quotes) → escaped or wrapped, no SQL error.
- Integration: F2 header query → inject_context surfaces error-related memories at top of bullet list.

**Verification:** With a query argument, FTS-matching memories surface ahead of unrelated high-exposure ones. Without a query, output identical to F1+F2 baseline.

---

- U5. **memdoctor structured signal codes**

**Goal:** Each detector returns a dict with `code`, `severity`, `safe_next_step` alongside existing fields. JSON output exposes them; report formatters surface them as a prefix.

**Requirements:** R5, R6

**Dependencies:** None (independent of U1–U4; can ship in any order)

**Files:**
- Modify: `tools/memdoctor.py` (each `detect_*` function + module-level constants + `run()` JSON branch + `_print_*` formatters)
- Test: `tests/test_memdoctor.py` (extend existing detector tests)

**Approach:**
- Add module-level constants: `CODE_CORRECTION_HEAVY = "correction_heavy"`, `CODE_RAPID_CORRECTIONS = "rapid_corrections"`, `CODE_KEEP_GOING = "keep_going"`, `CODE_ERROR_LOOP = "error_loop"`, `CODE_RESTART_CLUSTER = "restart_cluster"`.
- Each detector returns (or includes in its dict) `{"code": CODE_X, "severity": "low"|"medium"|"high", "safe_next_step": "<short string>"}`. Severity heuristics: error_loop=high, correction_heavy=high, rapid_corrections=medium, keep_going=medium, restart_cluster=low.
- JSON output (`run(json=True)`) merges these into the existing payload — additive only, no key removals.
- Human report prefixes each signal with `[severity:CODE]` (e.g., `[high:correction_heavy] 4 sessions flagged…`).

**Patterns to follow:**
- Existing detector dict shape — additive-only extension.

**Test scenarios:**
- Happy path: each detector emits `code` + `severity` + `safe_next_step` matching the constant.
- Edge case: empty events → detector returns empty dict (no crash, no extraneous code field).
- Integration: `run(json=True)` payload contains structured codes; existing keys still present (regression guard).
- Edge case: `_print_*` for empty signal → no `[severity:CODE]` prefix emitted.

**Verification:** JSON consumers see new fields without losing old. Human report shows severity-prefixed signals.

---

- U6. **F1 `_apply_negative_downweight` weights decrement by signal severity**

**Goal:** When a session is flagged by multiple signals, `_apply_negative_downweight` weights the per-topic decrement by the highest-severity signal: high=2, medium=1, low=0 (skip).

**Requirements:** R5

**Dependencies:** U5

**Files:**
- Modify: `tools/memdoctor.py` (`_apply_negative_downweight`, `_analyze_attribution` to thread severity)
- Test: `tests/test_negative_attribution.py` (extend `test_apply_negative_downweight_*` cases)

**Approach:**
- `_analyze_attribution` already aggregates `dict[str, int]` (topic → implicated-session count). Extend value to `dict[str, tuple[int, str]]` where second is highest severity seen across implicating sessions, OR keep count and add a second dict `topic → severity`.
- `_apply_negative_downweight` translates severity → weight: high=2, medium=1, low=0. SQL becomes `UPDATE memories SET exposure_count = MAX(0, exposure_count - ?) WHERE topic = ?` with the weight as the parameter. Floor at 0 unchanged.
- Threshold (`MIN_NEGATIVE_SESSIONS`) unchanged.

**Patterns to follow:**
- Existing `_apply_negative_downweight` y/N prompt + transaction shape.

**Test scenarios:**
- Happy path: high-severity attribution → exposure decrements by 2 (e.g., 5 → 3).
- Happy path: medium-severity attribution → decrements by 1 (current behavior preserved).
- Edge case: low-severity attribution → no decrement, n returned excludes that topic.
- Edge case: floor still 0 — high-severity on exposure_count=1 → result=0, not negative.
- Edge case: mixed-severity sessions for same topic → highest severity wins (high beats medium beats low).
- Regression: `MIN_NEGATIVE_SESSIONS` filter still applied (count < threshold → skip regardless of severity).

**Verification:** High-severity signals decrement faster than medium; low-severity flagged sessions don't decay innocent memories.

---

## System-Wide Impact

- **Interaction graph:** `MemoryDB.upsert_memory` ← `parse_digest_output` ← `_run_llm` digest branch ← PreCompact / UserPromptSubmit hooks. `MemoryDB.inject_context` ← `_on_session_start` (F2 header inputs feed query). memdoctor signals ← F1 attribution path.
- **Error propagation:** Migration failure (U1) is the only hard-stop path — all other units degrade gracefully (parser falls back to 3-field, supersede falls back to update-in-place if column missing, BM25 falls back to legacy ranking, codes default to old free-text on missing constants).
- **State lifecycle risks:** Supersede chains (U3) must run in single transactions to avoid orphaned old rows pointing at uncommitted new rows. F1 attribution table (`injections`) survives schema v4 with no changes.
- **API surface parity:** Both module-level `inject()` wrapper and CLI `inject` subcommand need the new `query` kwarg. memdoctor JSON output is consumed by external tooling — keep all old keys.
- **Integration coverage:** F1 (corrected sessions decrement injected topics) must continue to work after U3 (supersede) and U6 (severity weighting). Need at least one integration test seeding a corrected session, running `inject_context` → `detect_negative_attribution` → `_apply_negative_downweight` end-to-end on a v4 DB.
- **Unchanged invariants:** Schema v3 `injections` table layout untouched. SNAPSHOT_PROMPT JSON contract untouched (per `feedback_snapshot_enrichment` memory). `MIN_NEGATIVE_SESSIONS = 2` threshold unchanged.

---

## Risks & Dependencies

| Risk | Mitigation |
|------|------------|
| Schema v4 migration corrupts existing v3 DBs in user installs | Idempotent `if version < 4` block + `IF NOT EXISTS` / `ADD COLUMN`; test against fixture v3 DB. Pre-launch — no production users yet, but worth being clean for the launch cohort. |
| 6-field DIGEST_PROMPT confuses Sonnet, breaks 3-field output | Parser tolerates both forms; LLM-side instruction emphasizes "legacy form remains valid"; test fixture covers both. |
| Supersede chain explodes row count on noisy memories | Audit during launch; if growth is unbounded, add periodic `_Janitor` pass that prunes superseded rows older than N days. Out of scope for this plan but easy follow-up. |
| BM25 query reranking surfaces irrelevant FTS matches over high-quality memories | Weighted formula (0.4 BM25 / 0.4 exposure / 0.2 recency) keeps exposure as a strong term; eval via `eval_corrections.py` after launch; tune weights if regression. |
| Severity weighting (U6) makes F1 too aggressive on transient errors | High-severity threshold still requires `MIN_NEGATIVE_SESSIONS = 2` distinct sessions; floor=0 prevents over-decay. Monitor via `eval_corrections.py`. |
| `inject_context` signature change breaks callers | Default `query=None` preserves call sites; only `_on_session_start` opts in to query-aware mode. |

---

## Documentation / Operational Notes

- Update `tools/memcapture.py` module docstring to mention v4 + supersede semantics.
- README "How memory works" section needs a 1-paragraph note on supersede chain + structured fields once docs catch up — not blocking this plan.
- After all 6 units land, redeploy via `./install.sh` and update `project_pending_work.md` memory.

---

## Sources & References

- Panel verdict (3 lenses on Gentleman/engram features) — current conversation
- F1 plan: `docs/plans/2026-05-05-002-feat-negative-feedback-loop-plan.md`
- F2 plan: `docs/plans/2026-05-05-003-feat-snapshot-enrichment-plan.md`
- Memory: `feedback_snapshot_enrichment.md` (SNAPSHOT_PROMPT inviolate)
- Memory: `project_memdoctor.md` (5 signals already shipped)
- Project conventions: `.claude/CLAUDE.md` (schema bump pattern, `LATEST_SCHEMA_VERSION`)
