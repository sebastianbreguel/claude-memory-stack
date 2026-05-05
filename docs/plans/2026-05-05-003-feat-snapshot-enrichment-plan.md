---
title: "feat: Snapshot enrichment with git history + last error"
type: feat
status: active
date: 2026-05-05
---

# feat: Snapshot enrichment with git history + last error

## Overview

The PreCompact-driven snapshot already prepends a small `# Git state` header (current branch + dirty file count) onto the transcript chunk before the LLM summarizes it. This is good for spatial orientation but thin on temporal orientation — the next session starts knowing _where_ work is happening but not _what just happened_. Two cheap, deterministic signals close that gap: the last 3 git commits and the last error encountered in the session. Both already have helpers in the repo (`_git_state` for git access, `memdoctor.extract_error_context` + `normalize_error` for error extraction). This plan wires them into the existing prepended header — purely additive, no LLM-prompt change, no schema change, no new dependency.

---

## Problem Frame

When SessionStart injects the cached snapshot summary, the LLM-generated text gives the human-language version of "what was happening". The signal is good, but two facts are uniquely well-suited to deterministic capture (cheap, accurate, no LLM token cost):

- **Recent commits**: tell the next session what work just landed. The LLM never sees commit messages — they're not in the transcript chunk.
- **Last error**: tell the next session what was breaking. The LLM does see this in the chunk, but tends to lossily summarize it; a deterministic last-error line preserves the exact text.

Both are 3-5 line additions to the existing `# Git state` header. The LLM can then weave them into the JSON `summary`/`last_error` fields with higher fidelity. Net effect: better-grounded next-session handoff for ~+60 LOC.

---

## Requirements Trace

- R1. Extend the deterministic header prepended to the snapshot LLM chunk to include the last N commits (default N=3) on the current branch.
- R2. Extend the same header to include a normalized `last_error` line if any tool_result with `is_error=True` exists in the session transcript.
- R3. No regression on snapshot path latency: `git log` runs with the same 2s timeout already used by `_git_state`, and error extraction reuses parsed events.
- R4. No regression on existing fallback behavior — when git/error data is missing, the header still emits in the same shape it does today (or is omitted entirely when nothing useful exists).
- R5. Header format stays human-readable Markdown so the LLM treats it as context, not noise.

---

## Scope Boundaries

- Not changing the SNAPSHOT_PROMPT JSON schema. The LLM still emits `{task, files, last_error, summary}`. The new header just gives it better source material.
- Not surfacing recent commits / last_error through `engram doctor` or any new CLI command — only through the snapshot pipeline.
- Not adding a "last failing test" field separate from `last_error`. If the last error came from a pytest tool_result, the existing extraction already captures it; an extra parser would add noise without precision.
- Not changing the digest pipeline header. Digest mode already runs against shorter chunks at higher frequency; enrichment lives in the snapshot path only.
- Not persisting recent_commits or last_error into `compactions` table. The header is consumed by the LLM in the same call that produces the snapshot JSON; persisting the raw header on top would duplicate the JSON's `last_error` field.

---

## Context & Research

### Relevant Code and Patterns

- `tools/engram.py:565` — `_git_state(cwd, timeout=2)`. Returns `{"branch": str|None, "dirty_files": int}`. Same pattern (small dict, best-effort, short timeout) is the right shape for the new helper or extension.
- `tools/engram.py:596` — `_run_llm`. Snapshot branch already has the header prepend at lines 606-610: `if args.mode == "snapshot": git = _git_state(...); if git["branch"] or git["dirty_files"]: header = ...; chunk = header + chunk`. F2 lives inside this block.
- `tools/engram.py:_cwd_from_transcript` — already used to resolve `cwd` from the transcript path. Reuse.
- `tools/memdoctor.py:288` — `extract_error_context(events) -> str | None`. Returns the text of the last `tool_result` with `is_error=True`. Exactly the right primitive.
- `tools/memdoctor.py:305` — `normalize_error(text) -> str`. Strips paths and caps at 200 chars. Use to keep header bounded.
- `tools/memdoctor.py:_extract_chunk` (via memcapture) and `parse_jsonl` already do transcript→events conversion; F2 needs to call `parse_jsonl` once on the same transcript path that `_run_llm` is already reading from.

### Institutional Learnings

- Pre-launch version discipline: direct push to main, no version bumps.
- Push workflow: scout/feature work on claude-engram pushes directly to main, no PRs unless requested.
- Test subprocess audit: any new behavior in tools/ needs both direct-import test and `subprocess.run([uv, run, ENGRAM, ...])` integration test.

### External References

- None needed. Every primitive this plan calls already exists in the repo.

---

## Key Technical Decisions

- **Extend the header, not the prompt.** `SNAPSHOT_PROMPT` already asks the LLM to emit `last_error`. We don't change the prompt — we give the LLM better raw material via the prepended Markdown header, which it already weighs as context. Lower risk than rewriting the prompt; the JSON contract holds.
- **Reuse `extract_error_context` + `normalize_error`.** Don't write a third error parser. `memdoctor` already has the canonical pair. The only friction is that `_run_llm` lives in `engram.py` and the helpers live in `memdoctor.py` — a single `import memdoctor` solves it (already imported elsewhere in `engram.py`).
- **Add `recent_commits` to `_git_state` rather than a separate helper.** They share the cwd argument, the 2s timeout, the OK/skip semantics. Keeping one helper avoids a parallel-helper class smell.
- **Default N=3 commits, no flag.** Pre-launch + obvious shape; if 3 turns out wrong, adjust the constant. No need for an env var or CLI flag in v1.
- **Header is omitted when all enrichment fields are empty.** If there's no branch, no dirty files, no commits, no last_error — emit nothing, exactly as today. Avoid a header-only-with-empty-lines edge.

---

## Open Questions

### Resolved During Planning

- *Should "last failing test" be its own field?* No — `extract_error_context` already returns the last failed `tool_result`, which is the test output when the failure was a test. Adding a parallel "is_test_failure" classifier costs more than it returns.
- *Where does the events list come from for error extraction?* `_run_llm` already reads the transcript via `_extract_chunk` (which is text), but error extraction needs structured events. Solution: call `memcapture.parse_jsonl(transcript)` (or memdoctor's, same parser) once, pass to `extract_error_context`. Tiny extra IO; same file is already on disk and being read.

### Deferred to Implementation

- Whether to use `--no-decorate --no-color` flags on `git log` — depends on local git config; safe defaults are likely fine but check at implementation time.
- Whether to truncate commit subjects (e.g., to 80 chars) before injecting. Probably yes; confirm during implementation by eyeballing real chunk output.

---

## Implementation Units

- U1. **Add `recent_commits` to `_git_state`**

**Goal:** `_git_state` returns `{"branch": ..., "dirty_files": ..., "recent_commits": list[str]}`. Each commit is a `git log -3 --oneline` line (truncated to ~80 chars). Failures fall back to `[]`, same as today's branch/dirty_files do for `None`/`0`.

**Requirements:** R1, R3, R4

**Dependencies:** none

**Files:**
- Modify: `tools/engram.py` (`_git_state` at line 565)
- Test: `tests/test_engram_cli.py` (add a `_git_state`-direct test using a real tmp git repo, plus a snapshot-path subprocess test)

**Approach:**
- Add a third `subprocess.run(["git", "-C", cwd, "log", "-3", "--oneline", "--no-decorate"], timeout=2)` invocation inside the same try/except that already runs `branch` and `status`.
- Parse stdout into a list of lines; truncate each at 80 chars to avoid bloat.
- Return `[]` on any failure (not a repo, git missing, timeout) — same posture as branch/dirty_files.

**Patterns to follow:**
- The existing two `subprocess.run` calls in `_git_state`. Match their `capture_output=True, text=True, timeout=timeout` shape exactly.

**Test scenarios:**
- Happy path: tmp git repo with 5 commits → `_git_state(cwd)` returns `recent_commits` of length 3.
- Edge case: tmp git repo with 1 commit → returns `recent_commits` of length 1.
- Edge case: tmp dir with no git repo → returns `recent_commits == []`.
- Edge case: cwd is not a directory → returns `recent_commits == []` (already covered by the existing early-return guard).
- Integration: subprocess run of `engram on-precompact` with `ENGRAM_SKIP_LLM=1` — confirms the new git call doesn't crash the precompact handler. Existing `test_on_precompact_captures_session` already covers the surrounding flow; add a sibling test that asserts `recent_commits` shows up in the `_git_state` direct return.

**Verification:**
- `_git_state(cwd)` returns the new `recent_commits` key for any input cwd, never raises, and never blocks the precompact pipeline beyond the existing 2s timeout.

---

- U2. **Enrich snapshot header with commits + last_error**

**Goal:** When `_run_llm` runs in snapshot mode, the prepended header includes (when available) the recent commits from U1 and a normalized last-error line extracted from the transcript events. When everything is empty, no header is prepended (existing behavior preserved).

**Requirements:** R2, R3, R4, R5

**Dependencies:** U1

**Files:**
- Modify: `tools/engram.py` (snapshot branch in `_run_llm`, ~line 606)
- Test: `tests/test_engram_cli.py` (snapshot-mode header test)

**Approach:**
- Inside the `if args.mode == "snapshot":` block:
  - Call `_git_state` (now returning `recent_commits`).
  - Parse the transcript once via `memcapture.parse_jsonl(transcript)` (or `memdoctor.parse_jsonl`, whichever is already in scope) and call `memdoctor.extract_error_context(events)` followed by `memdoctor.normalize_error(...)` if non-None.
  - Compose the header in the existing Markdown shape, appending two new sub-sections (`recent_commits` and `last_error`) only when present:
    ```
    # Git state
    branch: <branch or '-'>
    dirty_files: <n>
    recent_commits:
    - <hash> <subject>
    - <hash> <subject>
    last_error: <normalized text>
    ```
  - Skip emitting the header entirely only when *all four* fields (branch, dirty_files>0, recent_commits, last_error) are empty.

**Patterns to follow:**
- Existing snapshot-branch header construction at `tools/engram.py:608-610`.
- Header shape mirrors the current `branch:`, `dirty_files:` lines so the LLM sees one familiar block, not two.

**Test scenarios:**
- Happy path: monkeypatch `_git_state` to return `{"branch": "main", "dirty_files": 1, "recent_commits": ["abc feat: x", "def fix: y", "ghi docs: z"]}` and a transcript fixture with a failing tool_result; assert the chunk passed to `_run_claude` (capture via monkeypatch) contains `recent_commits:`, the three commit lines, and `last_error: <normalized>`.
- Happy path: monkeypatch `_run_claude` to return `'{"task":"x","files":[],"last_error":null,"summary":"y"}'` and assert the snapshot ingestion still completes.
- Edge case: no commits, no errors, no dirty files, no branch → no header prepended (chunk passed to `_run_claude` is unchanged from `_extract_chunk` output).
- Edge case: only `last_error` present, no git data → header includes only `last_error:` line (no orphan `branch: -` if everything else is empty).
- Edge case: `last_error` text contains `/Users/...` paths → normalized to `<path>` via `normalize_error`.
- Integration (subprocess): `engram _run-llm --mode snapshot --transcript <fixture> --session-id sid --project p` with `ENGRAM_SKIP_LLM=1` — confirms wiring runs end-to-end without crash.

**Verification:**
- Snapshot pipeline still produces the same JSON shape from the LLM (no prompt change).
- The Markdown header passed to the LLM contains the new fields when source data exists.
- No new uncaught exceptions when transcript is malformed or git is missing.

---

## System-Wide Impact

- **Interaction graph:** PreCompact → fire-and-forget `engram _run-llm --mode snapshot`. F2 only modifies what's prepended to the LLM chunk inside that fire-and-forget child. No hook entry points change. Digest path unchanged.
- **Error propagation:** All new calls (`git log`, `parse_jsonl`, `extract_error_context`, `normalize_error`) are wrapped in best-effort try/except already present in their callers. A failure degrades to "header omits this field"; nothing crashes the snapshot.
- **State lifecycle risks:** None new. The transcript file is read twice now (once for chunk, once for events). On a 12k-char chunk transcript, this is negligible IO.
- **API surface parity:** `engram doctor` and other CLI surfaces unchanged. `_git_state` gains a key but existing callers don't read it; backward-compat at call sites is preserved by Python dict's open-ended semantics.
- **Integration coverage:** The `test_on_precompact_captures_session` flow already exercises end-to-end PreCompact under `ENGRAM_SKIP_LLM=1`. Adding one snapshot-mode subprocess test pins the new wiring.
- **Unchanged invariants:** SNAPSHOT_PROMPT text unchanged. JSON schema produced by the LLM unchanged. Compactions table schema unchanged.

---

## Risks & Dependencies

| Risk | Mitigation |
|------|------------|
| `git log` adds latency on slow disks. | 2s timeout already used by `_git_state`'s other calls; same posture. Any timeout falls back to `[]`. |
| Header bloat dilutes the LLM's attention on the transcript chunk. | Hard cap: 3 commits × ~80 chars + 1 normalized error × 200 chars = ≤ 440 chars added. Compared to the 12k-char chunk budget, < 4% of input. |
| `extract_error_context` returns a noisy multi-screen Python traceback. | `normalize_error` already strips paths and caps at 200 chars. Same primitive used by `memdoctor`. |
| Transcript file is missing or malformed during snapshot. | `parse_jsonl` already returns `[]` on parse failures. `extract_error_context([])` returns `None`. Header gracefully drops the field. |

---

## Documentation / Operational Notes

- README mention of "what's in the snapshot" if/when it gets one. Defer.
- Update `project_pending_work.md` memory to mark F2 shipped after the commit lands.

---

## Sources & References

- F1 plan (just shipped): `docs/plans/2026-05-05-002-feat-negative-feedback-loop-plan.md`
- Origin scout report: `karpathy-scout-sebastianbreguel-claude-engram.md`
- Related code: `tools/engram.py` (`_git_state`, `_run_llm`, `SNAPSHOT_PROMPT`), `tools/memdoctor.py` (`extract_error_context`, `normalize_error`)
- Pending-work memory: `project_pending_work.md`
