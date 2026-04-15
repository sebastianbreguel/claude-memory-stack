# Changelog

## Unreleased

### Added
- **Executive summary** at SessionStart: Sonnet merges Claude Code's `※ recap` (`away_summary`) with engram's inject_context into a single `next: <step>` line, cached per-project at `~/.claude/engram/executive/<cwd-slug>.md`. Read on SessionStart with zero latency; rebuilt in background on PreCompact and every 25 prompts.
- **UserPromptSubmit hook** (`engram.py on-user-prompt`): counts prompts per session and fires mid-session digest + executive rebuild every `ENGRAM_DIGEST_EVERY` prompts (default 25). Keeps long sessions from going stale even without a PreCompact event.
- `engram preview` subcommand: prints (and builds if missing) the executive cache for the current `cwd`. Useful for debugging.

### Changed
- LLM calls now use Sonnet 4.6 (was Haiku 4.5). Haiku hit `Prompt is too long` on large contexts; Sonnet handles the merge reliably.

### Fixed
- Fire-and-forget subprocesses pass arguments as `--flag=value` (inline form) instead of `--flag value` (separate tokens). Project slugs like `-Users-sebabreguel-...` start with `-` and were mis-parsed as another flag by argparse, producing `expected one argument` errors on every PreCompact / UserPromptSubmit rebuild.

### Changed (previous drop)
- Consolidated 5 shell hooks into 2 inline `engram.py` invocations (`on-precompact`, `on-session-start`). Net -381 lines.
- Pass A LLM calls now use Haiku 4.5 (was Sonnet).
- Removed semantic error regex from session capture; now relies only on Claude Code's `is_error=true` tool-result signal.
- Collapsed 11 `_dispatch_*` wrapper functions into argparse's native `set_defaults(func=...)` pattern. `memcapture.run()` gained an explicit `out: TextIO` parameter so callers control stdout without `sys.stdout` swapping.
- Unified `_run_digest` / `_run_snapshot` into a single `_run_llm` driven by `_LLM_MODES` dict. Internal `_run-llm --mode {digest,snapshot}` subcommand replaces two separate ones.
- `_extract_chunk` now streams with `collections.deque(maxlen=tail_lines)` instead of loading the entire file into memory. Prevents OOM on large transcripts.

### Fixed
- All timestamps now use `datetime.now(timezone.utc)` — previously mixed naive and aware datetimes.
- Project-scoped LIKE queries now escape `%` and `_` wildcards via `_like_escape()` + `ESCAPE '\'`. Prevents cross-project memory leaks on paths like `my_project`.
- `parse_digest_output` deduplicates same-topic lines within a single batch (last wins). Prevents duplicate memories when Haiku emits the same topic twice.
- HANDOFF paragraphs capped at 2000 chars to prevent runaway injection.
- `install.sh` `ensure_hook` now scans all matcher entries (not just empty-matcher) before adding a hook, preventing duplicates when users have custom matchers.
- Silent LLM failures now log to `~/.claude/engram.log` with UTC timestamps (missing `claude` binary, timeouts, non-zero exit).

### Removed
- `engram dashboard` subcommand and `memdashboard.py` — 1,610 lines of HTML generation removed. Second-order concern; may return as a lightweight standalone tool.
- `engram compile` and `engram export-concepts` subcommands. `memcompile.py` is no longer installed.
- `jq` is no longer a runtime dependency (all shell scripts replaced by Python).

### Migration
Existing installs: run `./install.sh` again to migrate `settings.json` from the 5 legacy `.sh` hook entries to the 2 new `engram.py` entries. Old shell scripts are removed automatically. `memory.db` and `patterns/` are preserved.

### Design notes — v1 constraints
Explicit bets baked into this release, so users can judge them before reporting them as bugs:

- **Concurrency is a collision absorber, not coordination.** Two PreCompact hooks firing on the same session spawn up to 2 Haiku subprocesses each; `PRAGMA busy_timeout=5000` + `UNIQUE(topic)` on `memories` absorb the rare race at the cost of occasional redundant LLM calls. No lockfile. Acceptable at Haiku 4.5 prices and single-user scale.
- **Schema evolution is idempotent-ALTER only.** `facts` widens via `ALTER TABLE ADD COLUMN` for nullable typed fields. No `PRAGMA user_version` migration framework. v2 typed constraints will need one.
- **`mempatterns` runs on the *previous* session's memories.** PreCompact orchestration is: sync capture → fire-and-forget Haiku digest → sync patterns. Patterns reflect what Haiku wrote last compaction, not this one. By design, not a bug.
