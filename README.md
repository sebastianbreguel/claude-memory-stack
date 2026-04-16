# Claude-engram

**Claude forgets everything between sessions.** Your preferences, your project state, where you left off — gone the moment you close the terminal.

claude-engram fixes that. **~350 ambient tokens. No Docker, no API keys, no MCP.**

## What you see

When you open Claude Code, claude-engram injects a 3-bullet executive summary from your last session:

```
- status: claude-engram MVP+D2 completo, 79 tests passing
- last change: D2 error-loop enrichment con memory.db cross-reference
- next: fix install.sh memdoctor → translate EXEC_PROMPT → docs
friction: correction-heavy(4x), error-loop(2x) (run: engram doctor)
```

Three bullets, zero latency. The merge (recap + memory + patterns) happens in the background *between* sessions, so opening is instant. The optional `friction:` line surfaces when `memdoctor` detects active signals for the current project.

## How it works

claude-engram has two jobs: **remember** and **inject**.

1. **While you work** — two triggers capture state:
   - **Every 25 prompts** (UserPromptSubmit) — mid-session digest fires a background LLM pass to update memories.
   - **On compaction** (PreCompact) — transcript → SQLite; digest + snapshot + pattern wiki refresh; executive summary rebuild.
2. **Between sessions** — Sonnet merges Claude Code's own `※ recap` with engram's memories/patterns into a 3-bullet executive summary, cached per project.
3. **On session start** — the cached executive is injected (zero latency). Falls back to ~350-token inject if the cache is missing.

That's the core. No config, no commands to run. It works while you work.

## What it remembers

| | What | Example | Lifetime |
|---|---|---|---|
| **Handoffs** | Where you left off | *"Refactoring auth to JWT; signup still on old sessions"* | 7 days |
| **Preferences** | How you like to work | *"uses uv, not pip · responds in Spanish"* | Forever |
| **Patterns** | How you actually work | *files always edited together, recurring errors* | Updated on each session |

Handoffs and preferences are the core — they inject automatically on every session start. Patterns are a bonus: an Obsidian-compatible wiki in `~/.claude/patterns/` that detects file co-edits, recurring errors, and tool habits from your history. Browse it, ignore it, or use `/patterns` inside Claude Code to explore.

## Install

**Requirements:** [Claude Code](https://docs.anthropic.com/en/docs/claude-code), [uv](https://docs.astral.sh/uv/)

**As a Claude Code plugin (recommended):**

```bash
# In Claude Code:
/plugin install claude-engram@sebastianbreguel/claude-engram
```

**Or clone and run the installer:**

```bash
git clone https://github.com/sebastianbreguel/claude-engram.git
cd claude-engram && ./install.sh
```

```bash
# Uninstall (keeps your memory.db data)
cd claude-engram && ./uninstall.sh
```

## Why not built-in memory?

Claude Code has auto-memory (`MEMORY.md`) — it stores what you explicitly tell it to remember. claude-engram watches what you *actually do*: it extracts decisions, errors, preferences, and project state from every session automatically. It scopes memories per project, detects workflow patterns across sessions, and rebuilds a structured executive summary so your next session starts exactly where you left off — without you lifting a finger.

## How it compares

| | claude-engram | claude-mem | OpenMemory | cortex |
|---|---|---|---|---|
| Ambient token cost | **~350** | ~2K+ | ~1K+ (MCP) | ~3K (27 tools) |
| External services | None | Agent SDK worker | Docker + MCP server | MCP server |
| API keys required | No | Yes | No | No |
| Runtime | Python + SQLite | Node worker | Docker | Rust binary |
| Install | `./install.sh` | npm + worker | docker compose | cargo |

## Privacy and transparency

Everything lives in `~/.claude/memory.db` (SQLite) and `~/.claude/patterns/` (markdown). Nothing leaves your machine.

- **Captured**: session metadata, files touched, tool usage, error strings, and LLM-extracted memories.
- **NOT captured**: no full transcripts, no code content, no secrets from `.env`.
- **LLM calls**: `claude --print` (Sonnet 4.6) on compaction + every 25 prompts (~2-5K tokens each, local to your session). No external API calls.
- **Uninstall**: `./uninstall.sh` removes tools and hooks. Your data is preserved unless you delete it.

## CLI

```bash
uv run ~/.claude/tools/engram.py --version          # print installed version
uv run ~/.claude/tools/engram.py verify-install     # check repo ↔ ~/.claude/tools in sync
uv run ~/.claude/tools/engram.py stats              # what claude-engram knows
uv run ~/.claude/tools/engram.py memories           # list learned memories
uv run ~/.claude/tools/engram.py forget "topic"     # delete one memory
uv run ~/.claude/tools/engram.py forget --expired --dry-run   # preview stale-ephemeral cleanup (>7d)
uv run ~/.claude/tools/engram.py forget --project X --dry-run # preview project-scoped cleanup
uv run ~/.claude/tools/engram.py search <query>     # FTS5 search over captured facts
uv run ~/.claude/tools/engram.py doctor             # friction signals (correction-heavy, error-loop, ...)
uv run ~/.claude/tools/engram.py preview            # current executive summary
uv run ~/.claude/tools/engram.py preview --prev     # rotated previous summary (safety net)
uv run ~/.claude/tools/engram.py log --tail 20      # tail background LLM failures
uv run ~/.claude/tools/engram.py patterns --report  # detected patterns
```

Full reference: [docs/cli-reference.md](docs/cli-reference.md).

## Optional: pattern detection

claude-engram detects emergent patterns from your session history — file pairs you always edit together, recurring errors, and tool habits. Patterns are stored as an Obsidian-compatible wiki in `~/.claude/patterns/`.

```bash
uv run ~/.claude/tools/engram.py patterns --report   # detected patterns
uv run ~/.claude/tools/engram.py patterns --status   # wiki stats
```

Use `/patterns` inside Claude Code to explore. Add substrings to `~/.claude/patterns/.ignore` to exclude noisy projects.

## Per-project scoping

claude-engram injects memories scoped to where you are:

- **Durable** (preferences, practices) — global, appear in any project
- **Ephemeral** (project state, handoffs) — scoped to the current project's cwd
- **Snapshots** — the last work-state snapshot, injected only for the matching project

Open `vambe-datascience` and you get vambe context. Switch to `claude-engram` and you get claude-engram context.

## Architecture

```
                              Claude Code hooks
            ┌──────────────────┬──────────────────┬───────────────────┐
            │  PreCompact      │  UserPromptSubmit│   SessionStart    │
            └────────┬─────────┴─────────┬────────┴─────────┬─────────┘
                     │                   │ (every 25)       │
                     ▼                   ▼                  ▼
            engram.py on-precompact  on-user-prompt   on-session-start
                     │                   │                  │
          ┌──────────┼──────────┐        │                  │
          ▼          ▼          ▼        ▼                  ▼
       [sync]    [async×3]  [sync]   [async×2]         [sync read]
     memcapture  Sonnet 4.6 patterns  digest           executive
                 ┌────────┐             + executive    cache read
                 │digest  │                            (~90 chars)
                 │snapshot│                               │
                 │executive│                              ▼
                 └────┬───┘                          additionalContext
                      │                              (invisible) +
                      ▼                              systemMessage
             ┌──────────────────────────┐            (banner)
             │       memory.db          │
             │  sessions, facts,        │
             │  memories (topic UPSERT) │
             │  compactions, files,     │
             │  tool_usage, facts_fts   │
             └──────────────────────────┘
             ┌──────────────────────────┐
             │  ~/.claude/patterns/     │  Obsidian wiki
             │  ~/.claude/engram/       │  executive cache
             │      executive/<slug>.md │  (one per project)
             └──────────────────────────┘
```

**Data flow:**
- **PreCompact:** transcript → SQLite (sync) → 3 detached Sonnet subprocesses (digest + snapshot + executive) → pattern wiki (sync)
- **UserPromptSubmit:** counter++; every 25 prompts → mid-session digest + executive rebuild (both fire-and-forget)
- **SessionStart:** read cached executive (`<cwd-slug>.md`) → inject as `additionalContext`. Falls back to full `memcapture --inject` + banner if cache is missing.
- **Concurrency:** no locks — `PRAGMA busy_timeout=5000` + `UNIQUE(topic)` absorb races; executive cache is overwrite-only.

**Files (4 Python, 0 external deps):**

| File | Lines | Role |
|---|---|---|
| `engram.py` | ~900 | CLI + hook orchestrator, Sonnet dispatch, prompt templates, executive cache |
| `memcapture.py` | ~1,200 | JSONL parser, SQLite schema, inject builder, FTS5 search |
| `mempatterns.py` | ~600 | Pattern detection (file co-edits, tool habits, errors), wiki generator |
| `memdoctor.py` | ~540 | Friction signal detector (correction-heavy, error-loop, restart-cluster, ...) |

## At a glance

![claude-engram — session memory for Claude Code](docs/claude-engram-explainer.svg)

## Docs

- [CLI Reference](docs/cli-reference.md) — all commands, token budget, manual install, experimental features
- [Architecture](docs/architecture.md) — file layout, SQLite schema, design principles
- [Privacy Policy](docs/privacy.md) — what's captured, what's not, zero network activity

## License

MIT
