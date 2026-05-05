---
title: "refactor: finish argparse.Namespace fakery removal + extract WikiWriter parse helpers"
type: refactor
status: active
date: 2026-05-05
origin: karpathy-scout-sebastianbreguel-claude-engram.md
---

# refactor: finish argparse.Namespace fakery removal + extract WikiWriter parse helpers

## Overview

Two small subtractive refactors selected from the karpathy-scout report (rows #1 and #2). Both are direct continuations of the compression sweep already in progress on `main` (commits `de0e0dc`, `8d40f14`, `330c68e`, `1d919ec`, `e034ffe`). Together: ~−38 LOC, no behavior change, no new dependencies, no API surface change for callers outside the repo.

## Problem Frame

The recent sweep removed `argparse.Namespace` fakery from `memcapture.py` and `mempatterns.py`. `memdoctor.py` was missed: `memdoctor.run` still takes a `Namespace` it could decompose into kwargs, and `engram.py` reconstructs a `Namespace` at the call site (line 1148-1152) and again inside `_preview` (line 727) just to pass it across module boundaries. This re-introduces an argparse coupling at module boundaries the recent sweep was trying to break.

Separately, `WikiWriter.write_entity_page` and `write_pattern_page` (`tools/mempatterns.py:48-181`) duplicate a parse-existing-markdown branch — both walk the file looking for a frontmatter scalar and a list of bullets under a known H2. The duplication is small but bacterial-shaped (textbook extract opportunity).

## Requirements Trace

- R1. `memdoctor.run` accepts kwargs only; no `argparse.Namespace` parameter.
- R2. `engram.py` calls `memdoctor.run` and `_on_executive` (from `_preview`) without constructing an `argparse.Namespace` at the call site.
- R3. The argparse subparser for `engram doctor` continues to dispatch correctly with all current flags (`--project`, `--rules`, `--per-project`, `--propose`, `--json`).
- R4. `engram preview --cwd X` continues to build the executive cache when missing, identical to today.
- R5. `WikiWriter.write_entity_page` and `write_pattern_page` keep their public signatures and existing-page merge semantics (first-seen preservation, history accumulation, dedup).
- R6. All 132 tests pass.
- R7. `prek run --all-files` is clean.

## Scope Boundaries

- Not splitting `memcapture.py`, `engram.py`, or `MemoryDB` (deferred per `feedback_cosmetic_refactors.md`).
- Not unifying `inject_context`'s two-SQL-path branch (scout row #3 — separate decision, separate plan).
- Not auditing the 121 `try/except` sites (scout row #4 — separate decision, separate plan).
- Not changing the `argparse` surface for `engram doctor` or `engram preview` — flag names, help text, and exit codes are identical before/after.
- Not changing `WikiWriter`'s `wiki_dir` constructor or `write_index` method.

---

## Context & Research

### Relevant Code and Patterns

- `tools/memdoctor.py:736` — `def run(args: argparse.Namespace) -> int`. Consumes only `args.project`, `args.rules`, `args.per_project`, `args.propose`, `args.json`.
- `tools/memdoctor.py` does **not** define `main`, `build_parser`, or `__main__` — it is imported only. Confirmed: no `tests/` subprocess invocation of `memdoctor.py`. (Per `feedback_test_subprocess_audit.md` — no port helpers needed.)
- `tools/engram.py:1148-1152` — current dispatch:
  ```
  dr.set_defaults(
      func=lambda a: memdoctor.run(
          argparse.Namespace(project=a.project, rules=a.rules, per_project=a.per_project, propose=a.propose, json=a.json)
      )
  )
  ```
- `tools/engram.py:727-728` — current `_preview` shim:
  ```
  ns = argparse.Namespace(cwd=cwd, project_key=cwd.replace("/", "-"))
  _on_executive(ns)
  ```
- `tools/engram.py:621` — `def _on_executive(args: argparse.Namespace) -> int`. Consumes only `args.cwd` and `args.project_key`.
- `tests/test_engram_cli.py:414, 460, 503` — call `mod._on_executive(ns)` directly with a hand-constructed `Namespace`. Public callable shape **must remain Namespace-compatible** (so we keep `_on_executive` as a thin wrapper around the new kwarg-pure function).
- `tools/mempatterns.py:48-118` — `WikiWriter.write_entity_page` parses `first_seen` (frontmatter scalar), bullets under `## Co-edited with`, bullets under `## Common errors`.
- `tools/mempatterns.py:120-181` — `WikiWriter.write_pattern_page` parses `first_detected` (frontmatter scalar), bullets under `## History`.
- `tests/test_mempatterns.py:467-572` — direct `WikiWriter.write_entity_page` / `write_pattern_page` calls assert merge, first-seen preservation, history preservation. Tests call public methods only — internal helper extraction is invisible to them.

### Institutional Learnings

- `feedback_cosmetic_refactors.md` — skip L-effort cosmetic refactors pre-launch. *Both units here are S-effort and continue an already-shipping sweep, so this rule does not apply.*
- `feedback_test_subprocess_audit.md` — before dropping `__main__` from a tool, grep `tests/` for subprocess invocations of that `.py`. *Verified: `memdoctor.py` has no `__main__` to drop and no subprocess test invocations exist. No port work needed.*
- `feedback_argparse_dash_values.md` — use `f"--arg={value}"` not `["--arg", value]` when value may start with `-`. *Not relevant here — we are removing CLI plumbing on the Python side, not adding shell invocations.*
- `feedback_subagent_model.md` — Sonnet 4.6 for any subagent dispatch. *Likely no subagents needed for this size of work.*
- `feedback_pre_launch_discipline.md` — main-branch work OK pre-launch; no version bumps. *Direct push to main applies (per `feedback_push_workflow.md`).*

### External References

None — pure-Python refactor against existing test coverage. No new framework or library context required.

---

## Key Technical Decisions

- **Keep `_on_executive(args)` as a thin Namespace-accepting wrapper around a new kwarg-pure `_build_executive(*, cwd, project_key)`.** Rationale: `tests/test_engram_cli.py` calls `_on_executive(ns)` directly with hand-constructed Namespaces (lines 414, 460, 503). Changing that public shape forces test churn for no win. The wrapper is 2 lines; the body becomes the kwarg-pure function. Net LOC still negative because `_preview` drops its own `Namespace` shim.
- **Refactor `memdoctor.run` to keyword-only kwargs (`*, project=None, rules=False, …`)**, not positional. Rationale: matches the call-site shape; positional args here add nothing and make the boolean flags read poorly.
- **Scope the `engram.py` dispatch lambda to a tiny named function** if it grows past one readable line. Rationale: `_patterns_dispatch` (line 1101) already follows this pattern locally.
- **Helpers in `mempatterns.py` are module-private (`_parse_md_bullets`, `_parse_frontmatter_scalar`)**, not class methods. Rationale: no `self` state used; bacterial-style stand-alone helpers match the recent `_Janitor` extract (`e034ffe`) and `_slugify` already at module scope.
- **No new public re-exports from `mempatterns`.** The helpers stay private; only the existing `WikiWriter` API is reachable from outside.

---

## Open Questions

### Resolved During Planning

- *Do tests subprocess-invoke `memdoctor.py`?* — No. `memdoctor.py` has no `__main__` and tests import symbols directly.
- *Do tests subprocess-invoke `_on_executive`?* — No, but they import-and-call `mod._on_executive(ns)`. So we keep the Namespace-accepting wrapper.
- *Should `memdoctor.run` keep a positional `args` overload for back-compat?* — No. The only caller is `engram.py`. No external consumers.

### Deferred to Implementation

- Final naming of the kwarg-pure executive helper (`_build_executive` vs `_run_executive` vs inlined). Decide while writing the diff based on adjacent naming.
- Whether `_parse_frontmatter_scalar` is worth extracting as a separate helper or inlined into `_parse_md_bullets`'s caller — depends on whether it stays a one-liner regex.

---

## Implementation Units

- U1. **Convert `memdoctor.run` to kwargs and drop both `engram.py` Namespace shims**

**Goal:** Eliminate the last three sites where `argparse.Namespace` is constructed or required at module boundaries inside the engram → memdoctor → executive call chain.

**Requirements:** R1, R2, R3, R4, R6, R7

**Dependencies:** none

**Files:**
- Modify: `tools/memdoctor.py` (signature of `run`, ~5 line changes inside body to read locals instead of `args.X`)
- Modify: `tools/engram.py` (lines 621, 727-728, 1148-1152 — split `_on_executive`, drop `_preview` Namespace shim, rewrite doctor lambda)
- Test: `tests/test_engram_cli.py` (no edits expected — `_on_executive(ns)` callable shape preserved via thin wrapper). `tests/test_memdoctor.py` (no edits expected — does not import `run`).

**Approach:**
1. In `tools/memdoctor.py`, change `def run(args: argparse.Namespace) -> int` to `def run(*, project: str | None = None, rules: bool = False, per_project: bool = False, propose: bool = False, json: bool = False) -> int`. Replace `args.project` → `project`, `args.rules` → `rules`, `args.per_project` → `per_project`, `args.propose` → `propose`, `args.json` → `json` inside the body.
2. In `tools/engram.py`, replace lines 1148-1152 with `dr.set_defaults(func=lambda a: memdoctor.run(project=a.project, rules=a.rules, per_project=a.per_project, propose=a.propose, json=a.json))`.
3. In `tools/engram.py`, split `_on_executive(args)`: extract the body into `_build_executive(*, cwd: str, project_key: str) -> int`, and reduce `_on_executive` to `def _on_executive(args): return _build_executive(cwd=args.cwd, project_key=args.project_key)`.
4. In `tools/engram.py:_preview`, replace lines 727-728 with `_build_executive(cwd=cwd, project_key=cwd.replace("/", "-"))`.
5. Remove `import argparse` from `tools/memdoctor.py` if no longer referenced.

**Patterns to follow:**
- `tools/mempatterns.py:562-580` — `update_now`, `status_now`, `report_now` already use `*, db_path=None, wiki_dir=None` kwarg-only style. Mirror it.
- `tools/engram.py:1101-1110` — `_patterns_dispatch` shows the small named-function pattern if the lambda grows.

**Test scenarios:**
- *Happy path:* `engram doctor` (no flags) prints summary report unchanged. *Covered by* `tests/test_engram_cli.py` doctor-related tests.
- *Happy path:* `engram doctor --rules` prints rules markdown.
- *Happy path:* `engram doctor --rules --per-project` prints per-project rules.
- *Happy path:* `engram doctor --propose` enters propose path.
- *Happy path:* `engram doctor --json` emits JSON payload.
- *Happy path:* `engram doctor --project some/path` filters correctly.
- *Happy path:* `engram preview --cwd $PWD` builds executive cache when missing — same return code, same stdout, same cache file.
- *Happy path:* `engram preview --cwd X --prev` reads rotated cache, never rebuilds. *Covered by* `tests/test_engram_cli.py:test_preview_prev_reads_rotated_cache`, `test_preview_prev_reports_missing_cleanly`.
- *Integration:* `mod._on_executive(ns)` (Namespace-style direct call from tests at `tests/test_engram_cli.py:414, 460, 503`) still returns `0` and writes the cache. *This is the load-bearing test for the wrapper-preservation decision.*

**Verification:**
- `uv run pytest` — all 132 tests green.
- `prek run --all-files` clean.
- `git diff` shows: `argparse.Namespace` count drops to **zero** in `tools/memdoctor.py` and the three target sites in `tools/engram.py` (621 wrapper kept; 727 + 1148-1152 gone). The remaining `argparse.Namespace` annotations on hook handlers (`_on_precompact`, `_on_user_prompt`, `_on_session_start`, etc.) are **untouched** — they receive real argparse-dispatched namespaces.
- Manual smoke: `./install.sh && engram doctor && engram doctor --json && engram preview --cwd $PWD` — outputs match HEAD.

---

- U2. **Extract `_parse_md_bullets` and `_parse_frontmatter_scalar` helpers in `mempatterns.py`**

**Goal:** Collapse the duplicated parse-existing-markdown branch shared by `WikiWriter.write_entity_page` and `write_pattern_page` into module-private bacterial helpers.

**Requirements:** R5, R6, R7

**Dependencies:** none (independent of U1; can ship in either order)

**Files:**
- Modify: `tools/mempatterns.py` (add 2 helpers near `_slugify`; collapse parse branches inside `WikiWriter.write_entity_page` and `write_pattern_page`)
- Test: `tests/test_mempatterns.py` (no edits expected — public method signatures and merge semantics unchanged)

**Approach:**
1. Add module-level `_parse_md_bullets(content: str, header: str) -> list[str]` near the existing `_slugify` helper. It walks lines, finds the line equal to `header`, then collects each line starting with `- ` until the next `## ` heading. Returns the bullet text minus the `- ` prefix.
2. Add `_parse_frontmatter_scalar(content: str, key: str, default: str) -> str` — a single regex `re.search(rf"{re.escape(key)}:\s*(\S+)", content)`, return group 1 or default. (If this stays a one-liner, inline it instead — decide while editing.)
3. In `write_entity_page` (lines 65-86), replace the `if page_path.exists(): ... in_errors / co_edits / first_seen ...` block with three calls:
   - `first_seen = _parse_frontmatter_scalar(content, "first_seen", today)`
   - co-edit bullets via `_parse_md_bullets(content, "## Co-edited with")` then re-parse the `[[slug]] — N sessions` shape into the existing `existing_co_edits` dict
   - `existing_errors = _parse_md_bullets(content, "## Common errors")`
4. In `write_pattern_page` (lines 136-151), replace the existing-page parse with:
   - `first_detected = _parse_frontmatter_scalar(content, "first_detected", today)`
   - `history_lines = _parse_md_bullets(content, "## History")`
5. Preserve the `co_edits` regex parse (`re.match(r"-\s+\[\[([^\]]+)\]\]\s+[—-]+\s+(\d+)\s+sessions?", line)`) — that one is structurally richer than a flat bullet and stays inline, but can run over the bullets returned by `_parse_md_bullets` instead of over raw `content.splitlines()`.

**Patterns to follow:**
- `tools/mempatterns.py:_slugify` — existing module-level helper style (small, pure, no `self`, named with leading underscore).
- `tools/memcapture.py:_Janitor` (commit `e034ffe`) — recent precedent for extracting helpers from a method-heavy class without changing public shape.

**Test scenarios:**
- *Happy path:* Fresh `write_entity_page` call creates page with correct frontmatter, co-edits, errors. *Covered by* `tests/test_mempatterns.py:test_entity_page_creation`.
- *Edge case:* Second `write_entity_page` call on same path merges co-edits, does not overwrite. *Covered by* `tests/test_mempatterns.py:test_entity_page_merge`.
- *Edge case:* `first_seen` is preserved across multiple writes. *Covered by* `tests/test_mempatterns.py:test_entity_page_preserves_first_seen`.
- *Happy path:* Fresh `write_pattern_page` writes frontmatter + history "first detected" entry. *Covered by* `tests/test_mempatterns.py:test_pattern_page_creation`.
- *Edge case:* Re-writing pattern page preserves `first_detected` and prepends a "reinforced" entry to history. *Covered by* `tests/test_mempatterns.py:test_pattern_page_update_preserves_first_detected_and_history`.
- *Edge case (new, optional):* `_parse_md_bullets(content, "## Missing")` on content without that header returns `[]`. *Likely covered transitively by `test_pattern_page_creation` (no `## History` present on first write) but a direct micro-test on the helper is cheap if behavior surprises.*
- *Edge case (new, optional):* `_parse_md_bullets` stops at the next `## ` heading and does not bleed into the following section. *Implicitly covered by* the existing entity-page tests because entity pages have both `## Co-edited with` and `## Common errors`.

**Verification:**
- `uv run pytest tests/test_mempatterns.py` — all green.
- `uv run pytest` — full suite green.
- `prek run --all-files` clean.
- `git diff tools/mempatterns.py` shows: net negative LOC; both writers' parse branches each shrink ~10 lines; two new helpers ~6 lines each; no public signature changed.

---

## System-Wide Impact

- **Interaction graph:** U1 changes the **internal** API between `engram.py` and `memdoctor.py` (kwargs instead of `Namespace`). External CLI surface (`engram doctor`, `engram preview`) is unchanged — argparse handles the user side; the kwargs change is purely module-private.
- **Error propagation:** No change. `memdoctor.run` returns ints (0/1) the same way; `_build_executive` returns ints the same way `_on_executive` does today.
- **State lifecycle risks:** `_preview` previously called `_on_executive(ns)`; the new path calls `_build_executive(...)` directly — same side effects (write `<slug>.md`, rotate `.prev`). No new ordering risk.
- **API surface parity:** `_on_executive(args)` callable shape is preserved deliberately for `tests/test_engram_cli.py` direct calls. Other hook handlers (`_on_precompact`, `_on_user_prompt`, `_on_session_start`) are out of scope and stay `argparse.Namespace`-typed because they are only ever invoked by argparse dispatch.
- **Integration coverage:** No new mocks. Existing direct-call tests cover the wrapper-preservation contract.
- **Unchanged invariants:** Argparse subparser shape for `engram doctor` (all flags, all help text, exit code semantics) is unchanged. WikiWriter's public methods (`write_entity_page`, `write_pattern_page`, `write_index`, `__init__(wiki_dir=...)`) are unchanged. SQL schema, `~/.claude/memory.db`, `~/.claude/patterns/`, hook registration in `hooks/hooks.json` — all untouched.

## Risks & Dependencies

| Risk | Mitigation |
|------|------------|
| `memdoctor.run` is imported from a third place we didn't grep (e.g., installed `~/.claude/tools/memdoctor.py` from a stale install) | Verify with `grep -rn 'memdoctor.run' tools/ tests/` before commit. If anything outside `tools/engram.py` calls it, decide explicitly: keep a thin Namespace-accepting wrapper, same pattern as `_on_executive`. |
| A test we missed asserts on `memdoctor.run`'s `args` attribute access | Run full pytest before commit; failure surfaces it cleanly. Risk is bounded — only affected file is `memdoctor.py`. |
| `_parse_md_bullets` regex breaks on edge cases not covered by existing tests (e.g., bullets containing `## ` literal in the text) | The current code has the same edge case (it walks line-by-line looking for `startswith("## ")`). Helper preserves that exact behavior, not improves it. Same risk surface, no worse. |
| Two commits land out of order and the second hits a state the first hasn't reached | Both units are independent (`U2` does not depend on `U1`). Either can ship first. Recommend U1 first to keep the namespace sweep in one logical commit chain, but ordering is not load-bearing. |

## Documentation / Operational Notes

- After merging, run `./install.sh` locally to deploy to `~/.claude/tools/`. Per `CLAUDE.md` project convention.
- No `CONTRIBUTING.md`, `README.md`, `CLAUDE.md` updates needed — this is internal refactor with zero user-facing change.
- No version bump (pre-launch discipline per `feedback_pre_launch_discipline.md`).
- Direct push to `main` per `feedback_push_workflow.md`.

## Sources & References

- **Origin document:** `karpathy-scout-sebastianbreguel-claude-engram.md` (rows #1 and #2 of the ranked table)
- Related precedent commits: `de0e0dc` (drop argparse.Namespace fakery, memcapture/mempatterns kwargs), `8d40f14`/`330c68e`/`1d919ec` (drop redundant `build_parser/main/__main__` scaffolding), `e034ffe` (extract `_Janitor` helper from MemoryDB)
- Memory: `feedback_cosmetic_refactors.md`, `feedback_test_subprocess_audit.md`, `feedback_subagent_model.md`, `feedback_push_workflow.md`, `feedback_pre_launch_discipline.md`
