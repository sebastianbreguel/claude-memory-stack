# karpathy-scout — sebastianbreguel/claude-engram

_Run: 2026-05-05. Scope: pre-launch. Graph: 14 files, 346 nodes (Apr 28 stats), incrementally refreshed for current HEAD. Owner = solo dev pushing direct to main._

## shape & vibe

- **prod LOC (tools/)**: 4057 across 5 files. memcapture.py 1302, engram.py 1196, memdoctor.py 751, mempatterns.py 591, eval_corrections.py 217.
- **test LOC**: 2394 (~0.6× prod). 4 test files, 132 tests passing per memory.
- **prod deps**: zero. Stdlib + sqlite + `claude` CLI subprocess. Dev: pytest, ruff. *Already karpathy-shaped on the dependency axis.*
- **ceremony density**: 0 ABCs, 0 dataclasses, 0 logging-module usage, 0 Pydantic. argparse: 24 hits (one CLI per tool). `try/except`: 121 hits (high; some defensive, sample below).
- **architecture**: 3 communities (`tests-session` 165, `tools-detect` 155, `demo-wait` 12). **Zero cross-community edges, zero coupling warnings.** Loose coupling already real.
- **recent direction**: last 10 commits dominated by *refactor: drop scaffolding / fakery / extract helper*. Owner is actively compressing.

## karpathy diagnostic (60s read)

ok so this codebase is already pretty karpathy. zero prod deps, no ABCs, no logging module, no pydantic, three loosely-coupled directory-communities with no cross-edges. that's good. owner just spent the last week doing exactly the work karpathy would do — killing argparse.Namespace fakery and `build_parser/main/__main__` boilerplate from memcapture and mempatterns, extracting `_Janitor` from MemoryDB. the bias is correct.

what's left? *the same refactor wasn't finished.* `memdoctor.run(args: argparse.Namespace)` still takes the namespace; `engram.py:1148` reconstructs one (`argparse.Namespace(project=a.project, rules=a.rules, per_project=a.per_project, propose=a.propose, json=a.json)`) just to pass it back. and `engram.py:727` builds another fake namespace inside `_preview` to call `_on_executive`. dead patterns walking. then `WikiWriter` has two ~70-line page writers (entity, pattern) that share the same parse-existing → merge → render-template structure — extractable into a tiny bacterial helper. and `inject_context` runs two SQL queries that differ only in WHERE/ORDER — unifiable. that's the residue. it's small. *i cannot simplify this any further* is close. don't pad. once the namespace finish-the-job lands, this repo is at lean baseline and further compression starts taxing clarity.

## owner / maintainer profile

- 50 commits total, 50 in last 6 months → all activity is recent
- merged PRs: only 4 (#1, #2, #4, #5) — all shipped by codex agent on small CI/UX scope. **Solo dev pushes direct to main** (memory rule). Confidence in PRs as signal: *low*; better signal = direct commits.
- recent direct-commit pattern (last 10): *refactor*, *refactor*, *docs*, *docs*, *refactor*, *refactor*, *refactor*, *refactor*, *chore*, *feat*. ~70% subtractive/compressive. Owner currently rewards: ceremony removal, scaffolding drops, helper extraction. Owner currently rejects: cosmetic-only refactors (deferred #15 split MemoryDB, #16 Hook classes per memory).
- closed-unmerged: empty.
- open PRs: empty (no WIP collisions).
- **inferred bar**: aligned proposals = continue refactor sweep that's already in motion; misaligned = "let's split a 1200-line file because it's big" without a behavior justification.

## the table

| # | Proposal | Filter | Kind | Anchor | Net LOC | Karpathy | Maintainer | Impact | Effort | Combined |
|---|----------|--------|------|--------|---------|----------|------------|--------|--------|----------|
| 1 | finish argparse.Namespace fakery removal: convert `memdoctor.run` to kwargs + drop the two Namespace shims in engram.py | ceremony | compress | tools/memdoctor.py:736 + tools/engram.py:727,1148 | −18 | 88 | 92 | Medium | S | 87 |
| 2 | extract `_parse_md_section(content, header)` helper from `WikiWriter.write_entity_page` and `write_pattern_page` (template parsing duplicated) | bacterial | compress | tools/mempatterns.py:48-181 | −20 | 75 | 80 | Low | S | 70 |
| 3 | unify `inject_context` two-SQL-path branch into one query with project-aware ORDER (or a single-pass python sort over rows) | compression | compress | tools/memcapture.py:471-508 | −18 | 70 | 55 | Medium | S | 64 |
| 4 | audit `except Exception: pass` swallows in tools/ (121 try/except total; spot-checked engram.py:580 silently drops pattern errors) | slop | compress | tools/*.py (~6 sites est.) | −5 to −12 | 65 | 60 | Low | M | 56 |

four rows. all subtractive (kind=compress, all net LOC negative). subtractive ratio 100%, well above the 70% floor. no padding with additive proposals because there is no missing first-order term that justifies one — the codebase has the exec-cache, banner, doctor, patterns, eval already.

## per-opportunity detail

### #1 — finish argparse.Namespace fakery removal

**why karpathy would do it:** "you started this. last week you killed exactly this pattern from memcapture and mempatterns. memdoctor still has it and engram.py is reconstructing namespaces just to pass them across module boundaries. dependencies bad bad bad — passing argparse.Namespace into another module's API makes that module depend on argparse for no reason. just take kwargs."

**graph evidence:**
- `memdoctor.run(args: argparse.Namespace)` at tools/memdoctor.py:736 — only consumes `args.project, args.rules, args.per_project, args.propose, args.json`
- `engram.py:1148-1152` — `lambda a: memdoctor.run(argparse.Namespace(project=a.project, rules=a.rules, per_project=a.per_project, propose=a.propose, json=a.json))` (4 lines reconstructing what was just decomposed)
- `engram.py:727` — `ns = argparse.Namespace(cwd=cwd, project_key=cwd.replace("/", "-")); _on_executive(ns)` inside `_preview`
- impact radius (memdoctor.py + engram.py): 214 impacted nodes within 2 hops, but the actual API surface change is local — only `engram.py` calls `memdoctor.run` from outside, and `_preview` is the only non-CLI caller of `_on_executive`

**diff sketch:**
```python
# memdoctor.py
def run(*, project: str | None = None, rules: bool = False,
        per_project: bool = False, propose: bool = False, json: bool = False) -> int: ...

# engram.py:1148
dr.set_defaults(func=lambda a: memdoctor.run(
    project=a.project, rules=a.rules, per_project=a.per_project,
    propose=a.propose, json=getattr(a, "json", False),
))

# engram.py:727 — split _on_executive into a kwarg-pure body + a Namespace-thin wrapper
def _build_executive(*, cwd: str, project_key: str) -> int: ...
def _on_executive(args): return _build_executive(cwd=args.cwd, project_key=args.project_key)
# _preview now: _build_executive(cwd=cwd, project_key=cwd.replace("/", "-"))
```

**e2e test plan:**
1. preconditions: existing 132 tests, no new env
2. trigger: `uv run pytest`
3. expected: all green (memdoctor tests already construct Namespaces; either update them to kwargs or keep a thin Namespace wrapper around the kwarg fn for back-compat in tests)
4. manual: `engram doctor --rules`, `engram doctor --json`, `engram doctor --propose`, `engram preview --cwd $PWD` — outputs unchanged
5. tooling: pytest + ruff already in CI

**maintainer note:** STRONGLY ALIGNED. Owner shipped this exact refactor for memcapture (de0e0dc) and the three sibling tools' `build_parser/main/__main__` drops (8d40f14, 330c68e, 1d919ec) in the last week. memdoctor was the one that didn't get the kwargs treatment because it has its own `build_parser/main/__main__` still in use; the kwargs split is the next chip. Confidence: very high.

---

### #2 — extract `_parse_md_section` helper from `WikiWriter`

**why karpathy would do it:** "two functions, both ~70 lines, both do `if page_path.exists(): parse known-headers, accumulate; else: defaults`. that pattern is bacterial — small, modular, copy-pasteable into a one-liner. extract it once, both writers shrink. don't extract a class. don't extract an ABC. one function. small."

**graph evidence:**
- `write_entity_page` (mempatterns.py:48-118): parses `first_seen`, `## Co-edited with` items, `## Common errors` items
- `write_pattern_page` (mempatterns.py:120-181): parses `first_detected`, `## History` items
- both follow: read text → regex frontmatter scalar → walk lines collecting bullets under known H2 → merge → re-render. textbook duplication

**diff sketch:**
```python
def _parse_md_bullets(content: str, header: str) -> list[str]:
    out, in_section = [], False
    for line in content.splitlines():
        if line.strip() == header: in_section = True; continue
        if in_section:
            if line.startswith("## "): break
            if line.startswith("- "): out.append(line[2:])
    return out

def _parse_frontmatter_scalar(content: str, key: str, default: str) -> str:
    m = re.search(rf"{key}:\s*(\S+)", content)
    return m.group(1) if m else default
```
Both writers collapse their existing-page branch by ~10 lines each.

**e2e test plan:**
1. existing `tests/test_mempatterns.py` covers entity-page merge, pattern-page history, first-detected preservation — all hit the parse paths
2. trigger: `uv run pytest tests/test_mempatterns.py`
3. expected: green unchanged

**maintainer note:** ALIGNED. Owner did `_Janitor` extract from MemoryDB (e034ffe) — same shape (private helper for repeated parse logic). Lower-priority than #1 because mempatterns isn't in the active refactor sweep this week.

---

### #3 — unify `inject_context` two-SQL-path branch

**why karpathy would do it:** "two SELECTs that differ only in `LEFT JOIN sessions` + `CASE WHEN s.project LIKE` + extra ORDER column. that's not two queries. that's one query where the project case is a parameterized score component. half the SQL real estate is paying for the branch."

**graph evidence:**
- `MemoryDB.inject_context` tools/memcapture.py:471-589 (119 lines, biggest function)
- lines 482-508: 27 lines of duplicated SELECT scaffolding for the project-vs-no-project branch

**diff sketch:** always select with `LEFT JOIN sessions`, parameterize the `CASE WHEN project IS NULL OR durability='durable' THEN 1 ELSE LIKE-match END` with a sentinel `'%'` when project is None. Or: do one unconditional fetch and let python sort by `(durable_or_project_match desc, score desc)`. Both shave ~18 LOC.

**e2e test plan:**
1. existing `tests/test_e2e.py::test_project_scoped_inject_surfaces_handoff` and `test_inject_includes_active_patterns` cover both branches
2. trigger: `uv run pytest tests/test_e2e.py -k inject`
3. risk: SQL clarity — if the unified query becomes harder to read than the branch, abort. measure twice

**maintainer note:** NEUTRAL → ALIGNED. SQL-readability sensitivity is per-call; owner already added pyproject `E501` exemptions for SQL strings, signaling SQL clarity is valued over line-count compression. Score is honest: lower confidence than #1/#2.

---

### #4 — audit defensive `except Exception: pass` swallows

**why karpathy would do it:** "121 try/except in 4057 LOC is high. some are real (SessionStart hook must not crash on schema-version refusal — that's intentional, lines 1006-1041). but `inject_context` line 580 silently swallows every error from `_read_active_patterns` — what's that protecting against? if the patterns wiki dir has bad permissions you want to know, not silently lose your patterns banner. spot-audit, keep the load-bearing ones, delete the slop."

**graph evidence:** spot sample
- `tools/memcapture.py:576-581`: `try: patterns = self._read_active_patterns(); ... except Exception: pass` — silent swallow
- `tools/engram.py:988-991, 1001-1004`: `try: payload = json.loads(raw) except Exception: payload = {}` — bare-except where `json.JSONDecodeError` would do
- `tools/engram.py:1014-1041`: schema-error catch chain — load-bearing (intentional, documented)

**diff sketch:** narrow `except Exception` → `except (json.JSONDecodeError, OSError)` etc. delete pure pass-swallows where the surrounding code already runs in a hook with its own outer guard.

**e2e test plan:** narrow scope; tests should be unaffected. risk: introducing real exceptions in code paths that weren't previously surfaced. needs careful per-site judgment, hence Effort=M.

**maintainer note:** NEUTRAL. Owner has not done this kind of audit recently; it's slow per-site work and easy to break SessionStart-style critical paths. Honest read: low priority unless paired with a specific friction signal from `engram doctor`.

## what's NOT in the table (and why)

- **split memcapture.py 1302 / engram.py 1196 / MemoryDB into modules** — DEFERRED per memory (`feedback_cosmetic_refactors.md`). Cosmetic L-effort. Owner explicitly said no until post-launch. Karpathy might agree-skip too: 3 communities, 0 cross-edges, file size alone ≠ split.
- **pure-additive features** (new doctor signals, new banner panes, telemetry, etc.) — no first-order term currently missing. claude-engram already does capture, inject, patterns, doctor, eval-corrections, exec-summary, snapshot. adding more = pre-launch noise. compression is the move.
- **drop a dep** — already 0 deps. nothing to drop.
- **type-hint expansion / ABC introduction / dependency-injection** — anti-proposals.

## summary

- **diagnostic**: claude-engram is already lean. four small subtractive opportunities remain, total ~−61 LOC. once #1 ships the codebase is at karpathy-baseline pre-launch.
- **top-3 by combined**: (1) finish Namespace-fakery removal (87), (2) WikiWriter `_parse_md_bullets` helper (70), (3) inject_context SQL unify (64).
- **report path**: `karpathy-scout-sebastianbreguel-claude-engram.md`
