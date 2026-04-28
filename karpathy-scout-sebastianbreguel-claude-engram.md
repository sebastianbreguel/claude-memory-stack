# karpathy-scout — claude-engram

> generated 2026-04-28 · `cwd=/Users/sebabreguel/personal/claude-engram` · graph: 346 nodes / 3419 edges / 14 source files

## shape & vibe

| dim | value |
|---|---|
| total LOC (source) | ~6.7k |
| tools (the product) | 4077 LOC across 4 files |
| tests | ~2400 LOC across 4 files |
| **runtime deps** | **0** (`dependencies = []` in pyproject) |
| dev deps | `pytest`, `ruff` |
| python floor | 3.12 |
| logging module hits | 0 |
| dataclass / TypedDict / Protocol | 0 |
| argparse refs | 42 (concentrated in `engram.build_parser` + Namespace builders) |
| `try/except` density | ~50 (mostly intentional non-blocking around fire-and-forget LLM calls) |
| communities (graph) | 3 — tools (155), tests (165), demo-js (12). 0 cross-community edges |
| top-3 large funcs | `memcapture.run` 190L · `MemoryDB.inject_context` 119L · `engram.build_parser` 99L |

## karpathy diagnostic

ok this repo is already kind of embarrassing for a karpathy review in a good way. zero runtime deps. one single-file orchestrator (engram.py), three single-file tools, sqlite as the only side-channel, no docker, no MCP, no API keys, claude binary called via fire-and-forget subprocess. memory says 6 prior scout opps shipped/deferred and 3 of the last 4 commits literally delete scaffolding (`build_parser` / `main` / `__main__` from memcapture/mempatterns/memdoctor). the owner is doing the work. dependencies bad bad bad — there are none.

so where's the meat. one place. **engram.py still pretends `memcapture.run(args: argparse.Namespace)` is the public API.** the recent refactor stripped the argparse front-door from memcapture but not the back-door it served. so engram.py builds a 19-field fake Namespace via `_memcap_ns(**overrides)` and hands it to `memcapture.run()`, which is a 190-line `if args.stats: ... elif args.query: ... elif args.recent: ...` dispatch. 13 call sites do this. it's a costume that nothing wears anymore. the natural next step in the arc the owner is already walking is: drop the costume, call functions directly. that's it. one proposal does ~70% of the remaining karpathy work on this codebase.

i cannot simplify this any further is genuinely close. the table below has 4 rows; it is **not** padded. one is the load-bearing one (#1). the rest are smaller compressions.

## owner / maintainer profile

last 6 months of merged PRs (4 total — solo project, most work via direct push):

| # | title | +/− | shape |
|---|---|---|---|
| 5 | pre-launch readiness — CONTRIBUTING + PR template + README badges | +105/−0 | docs/polish |
| 4 | pre-launch trim: friction banner, **demos 7→1**, atomic exec cache | +1129/−77 | **delete-heavy / consolidation** |
| 2 | regenerate centered demo GIFs | +1/−1 | ops |
| 1 | center HyperFrames demo preview | +28/−9 | ops |

direct-commit pattern (the actual signal): `refactor: drop redundant build_parser/main/__main__ scaffolding` (×3 tools), `refactor: extract _Janitor helper from MemoryDB`, `chore: bump python floor 3.11→3.12`, `perf: 8 latency wins on hot paths`, `feat: doctor --propose`, `cleanup: panel review fixes`. **strong delete/compress bias, anti-cosmetic, fast-merging.**

memory flags: pre-launch — version bumps and tags off-limits; cosmetic refactors deferred post-launch. pushes direct to main. no PRs unless asked.

## the table

| # | proposal | filter | anchor | karpathy | maintainer | impact | effort | combined |
|---|---|---|---|---|---|---|---|---|
| 1 | drop `_memcap_ns` / `_patterns_ns` Namespace fakery; replace `memcapture.run(args)` with kwarg-based module functions (`memcapture.search(q)`, `memcapture.stats()`, etc.); collapse the 190-line if/elif dispatch | ceremony + first-order + compression | `tools/engram.py:38` (`_memcap_ns`) + `tools/memcapture.py:1089` (`run`) | 92 | 80 | High | M | 86 |
| 2 | inline `_patterns_ns` into its single call site (or drop entirely after #1) | ceremony | `tools/engram.py:65` (`_patterns_ns`) + `tools/engram.py:1156` (only caller) | 70 | 80 | Low | S | 68 |
| 3 | merge `_read_counter` / `_write_counter` / `_reset_counter` into one tiny module-level helper or one class — 3 funcs for a single int file is more chrome than content | bacterial / compression | `tools/engram.py:447-466` | 55 | 55 | Low | S | 53 |
| 4 | review `MemoryDB.inject_context` (119 lines): is the `_fallback_inject` branch (54 lines) actually used in any test/path, or vestige of an earlier inject pipeline? if unused → delete | slop removal | `tools/memcapture.py:435` (`inject_context`) + `tools/memcapture.py:636` (`_fallback_inject`) | 60 | 70 | Medium | S–M | 64 |

> 4/4 rows are subtractive. 100% deletion/compression. no additive proposals. that's the right shape for this repo today.

> note: graph hub/bridge/knowledge-gap tools errored (`'NoneType' object has no attribute 'resolve'`) — likely a graph-state issue worth filing upstream to code-review-graph, but does not change conclusions: the architecture overview, communities, large-functions, and flows tools all worked, and serena grounded every anchor below.

---

## #1 — drop `_memcap_ns` / kwargs-not-Namespace + collapse `memcapture.run` dispatch

**why karpathy would do it:** "the costume is louder than the body. you stripped `build_parser` and `main` from memcapture three commits ago — but `run(args: argparse.Namespace)` is still wearing argparse drag. nothing parses argv into that Namespace anymore. engram.py *fakes* one (19 default fields, set 1–3 of them, hand it back). that's not an API, that's a 13-call-site lie about what the function does. delete the lie. call functions."

**graph evidence:**
- `tools/memcapture.py::run` — 190 lines (1089–1278), single-arg dispatch over `args.query`, `args.stats`, `args.recent`, `args.inject`, `args.banner`, `args.ingest_digest`, `args.ingest_snapshot`, `args.compactions`, `args.memories`, `args.forget`, plus capture-mode (`args.transcript` / `args.all`) — 11 mutually-exclusive branches.
- `tools/engram.py::_memcap_ns` — 27 lines (38–63), 19 default fields. Sole purpose: feed `memcapture.run`.
- 13 call sites in `engram.py` — confirmed via `find_referencing_symbols`:
  - `_on_precompact:488`, `_run_llm:668`, `_on_executive:691`, `_forget:813`, `_on_session_start:1077`, `_on_session_start:1087` (×2), and 7 lambdas inside `build_parser` (1136, 1140, 1145, 1150, 1159, 1169, 1182).
- Tests use subprocess against `engram` CLI, not direct calls to `memcapture.run` — refactor is opaque to the test suite (`tests/test_engram_cli.py`, `tests/test_e2e.py` both `subprocess.run`).
- Communities: clean module separation already (`tools-detect` cohesion 0.16, 0 cross-community edges with tests/demo).

**diff sketch:**

`tools/memcapture.py`:
```python
# replace `def run(args, out=None, input_text=None, db=None) -> int:` (190 lines)
# with small module-level functions, each one branch from the if/elif:

def search(query: str, *, db: MemoryDB | None = None) -> int: ...        # ~10 lines
def stats(*, db: MemoryDB | None = None) -> int: ...                      # ~25 lines
def recent(n: int, *, db) -> int: ...                                     # ~6 lines
def inject(project: str | None, *, db, out=None) -> int: ...              # ~3 lines
def banner(project, name, *, db, out=None) -> int: ...                    # ~3 lines
def ingest_digest(session_id, project, text, *, db) -> int: ...           # ~10 lines
def ingest_snapshot(session_id, project, text, *, db) -> int: ...         # ~6 lines
def compactions(filter_str, *, db) -> int: ...                            # ~12 lines
def list_memories(pattern, *, db) -> int: ...                             # ~10 lines
def forget(topic, *, ephemeral=False, db) -> int: ...                     # ~6 lines
def capture(transcript=None, *, all=False, extract_facts=False, db) -> int: ...  # ~25 lines
```

each one opens its own `MemoryDB()` if `db is None` (extract a tiny `@contextmanager _opt_db(db)` if needed — or just dup the 3-line owns_db pattern). total: ~115 lines of small functions vs. 190-line monolithic dispatch. **net: −75 lines in memcapture.py.**

`tools/engram.py`:
```python
# delete _memcap_ns (lines 38-63, -27 lines)

# rewrite call sites (representative):
- memcapture.run(_memcap_ns(transcript=str(transcript)))
+ memcapture.capture(transcript=str(transcript))

- memcapture.run(_memcap_ns(stats=True))
+ memcapture.stats()

- memcapture.run(_memcap_ns(query=a.query))
+ memcapture.search(a.query)

- memcapture.run(_memcap_ns(inject=True, inject_project=project_key or None), out=buf, db=shared_db)
+ memcapture.inject(project_key or None, out=buf, db=shared_db)

- memcapture.run(_memcap_ns(**{cfg["ingest"]: True, "session_id": args.session_id, "project": args.project}), input_text=output)
+ # _run_llm: replace dict-keyed ingest dispatch with a small if/elif on cfg["ingest"]:
+ if cfg["ingest"] == "ingest_digest":
+     memcapture.ingest_digest(args.session_id, args.project, output)
+ else:
+     memcapture.ingest_snapshot(args.session_id, args.project, output)
```

**combined net:** −27 (drop `_memcap_ns`) + −75 (collapse dispatch) + ~−5 across cleaner call sites ≈ **−105 to −115 lines, zero behavior change**. and the code finally says what it does.

**e2e test plan:**
1. preconditions: `~/.claude/memory.db` present (or recreated by `MemoryDB()`); transcript fixtures already used by `tests/test_e2e.py`.
2. trigger: `uv run pytest -q` — the existing 600+ tests across `test_e2e.py` (subprocess against engram CLI), `test_engram_cli.py` (subprocess), `test_memdoctor.py`, `test_mempatterns.py`.
3. expected: all green unchanged. tests use subprocess invocation of `engram <subcommand>`, so they exercise the new direct-call path automatically.
4. regression check: smoke run hooks manually:
   - `uv run tools/engram.py on-session-start <<< '{}'` → JSON output well-formed
   - `uv run tools/engram.py stats` → expected counters
   - `uv run tools/engram.py search test` → no crash
5. tooling: pytest already in CI (.github/workflows). no new infra.
6. manual verification cmd:
   ```bash
   ./install.sh && uv run pytest -q && \
     uv run tools/engram.py stats && \
     uv run tools/engram.py memories
   ```

**maintainer note:** the owner shipped 3 PRs in the last week of *this exact arc* (`drop redundant build_parser/main/__main__ scaffolding` × 3). this proposal completes that arc. expected: high-confidence merge. only friction is the M-effort scope (touches one file's public surface + 13 call sites in another). bundle as a single PR — not a series — because the API change and the call-site updates need to land together.

---

## #2 — inline (or drop) `_patterns_ns`

**why karpathy would do it:** "you have one caller. write the namespace inline. or after #1, just call `mempatterns.update_now()` / `mempatterns.report_now()` directly."

**graph evidence:**
- `tools/engram.py::_patterns_ns` — 13 lines (65–75).
- 1 caller: `build_parser:1156` (`mempatterns.run(_patterns_ns(update=a.update, status=a.status, report=a.report))`).

**diff sketch:** delete `_patterns_ns`. either inline at the lambda (`argparse.Namespace(update=a.update, ...)`), or — better — add `def update(...)`, `def status()`, `def report()` to `mempatterns.py` and bypass the namespace entirely (rhymes with #1).

**e2e test plan:** `uv run pytest tests/test_mempatterns.py` plus `uv run tools/engram.py patterns --status` and `--update`. existing tests cover orchestrator paths.

**maintainer note:** trivial. would be a sub-PR or part of #1.

---

## #3 — collapse the 3-function counter helper

**why karpathy would do it:** "three module-level functions to read, write, reset a single int from one file. that's chrome. one helper class with `.read() / .bump() / .reset()` or even just two functions. or inline since the only caller is `_on_precompact`."

**graph evidence:**
- `tools/engram.py::_read_counter` (447–456), `_write_counter` (457–463), `_reset_counter` (464–469). 17 lines combined.
- callers concentrated in `_on_precompact` (the only place compaction count is mutated).

**diff sketch:**
```python
# replace 3 funcs (17 lines) with one tiny class:
class CompactionCounter:
    def __init__(self): self.path = Path.home() / ".claude" / "engram" / "compactions.json"
    def read(self) -> tuple[str, int]: ...   # 6 lines
    def bump(self, sid: str) -> None: ...    # 4 lines
    def reset(self) -> None: ...             # 2 lines
```
or inline reads/writes directly into `_on_precompact` since it is the only mutator.

**effort/impact:** small win, low impact.

**maintainer note:** marginal. not urgent. include only if bundled with #1 to avoid PR proliferation.

---

## #4 — verify `_fallback_inject` is still reachable; if dead, delete

**why karpathy would do it:** "`MemoryDB.inject_context` is 119 lines. it has a normal path *and* a `_fallback_inject` arm at 54 lines. if the fallback never fires in practice, that's 54 lines of code defending against a ghost. read the call graph, prove it triggers, or delete."

**graph evidence:**
- `tools/memcapture.py::MemoryDB.inject_context` — 119 lines (435–553).
- `tools/memcapture.py::MemoryDB._fallback_inject` — 54 lines (636–689).
- need: trace whether the conditional that selects `_fallback_inject` over the snapshot-based path is reachable in current SessionStart flows.

**diff sketch:** read `inject_context` end-to-end, identify the conditional, prove via tests + manual probe whether the fallback is dead. if dead → delete `_fallback_inject` + the conditional. if alive but rare → keep, but add a one-line comment with the *triggering condition* (cheap, prevents future scout from re-flagging).

**e2e test plan:**
1. add a temporary log line in `_fallback_inject` (`_log_warning("fallback_inject hit")`).
2. run full test suite: `uv run pytest -q` — does the log line ever fire?
3. run `engram on-session-start` against a few real `~/.claude/projects/*/` dirs — does it fire there?
4. if neither: delete and ship.
5. revert the log line either way.

**maintainer note:** lower karpathy score because the work is investigative before it's deletive — but if fallback is dead, this is a pure −54 line win with zero behavior change.

---

## also-considered, dropped

these were generated during the lens scan but did not survive:

| proposal | why dropped |
|---|---|
| split `engram.py` (1243 LOC) into `hooks.py` + `cli.py` + `cache.py` | memory says #16 deferred as cosmetic post-launch; owner's stated preference is **anti-cosmetic refactor pre-launch** — wait |
| split `memcapture.py` (1279 LOC) along `MemoryDB` / `TranscriptParser` / cli seam | memory says #15 deferred; same reason |
| drop argparse, switch to bare module-level config + sys.argv parsing | argparse already in stdlib, 10+ subcommands warrant it; the Poor Man's Configurator filter doesn't fire for a CLI of this fan-out |
| add type hints to all DB methods | **anti-proposal.** karpathy doesn't ask for type ceremony in research code; this isn't research code but it doesn't matter — adds nothing and the codebase is already legible |
| add `@dataclass` to `SessionData` | already simple, current shape is fine; dataclass would add ceremony |
| add a logging module | repo deliberately uses `_log_warning` (8-line append-to-file). adding `logging.getLogger` would be a regression |
| compress `_create_tables` (83 lines of SQL DDL) | SQL DDL is already as compact as SQL gets. don't compress |
| compress `_extract_chunk` (98 lines) | this is the **first-order term** for fact extraction. mass is well-spent |
| compress `_on_session_start` (87 lines) | already optimized — see commit `68c2529` ("8 latency wins on hot paths"). leave |

---

## summary

three lines, terse, max one karpathy quote:

1. **diagnostic:** zero runtime deps, three modules, owner is already deleting on the karpathy beat — only one structural smell remains: the 19-field argparse.Namespace fakery between engram.py and memcapture.run, which is "the costume the body stopped wearing."
2. **top-3 by combined rank:** #1 drop `_memcap_ns` + collapse `memcapture.run` dispatch (combined 86, ~−110 LOC) — #4 verify+delete `_fallback_inject` (combined 64, possibly −54 LOC) — #2 inline `_patterns_ns` (combined 68, trivial).
3. **report path:** `karpathy-scout-sebastianbreguel-claude-engram.md` (cwd).
