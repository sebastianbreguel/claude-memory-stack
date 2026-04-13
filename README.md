# engram

Give Claude Code persistent memory that learns from your sessions — what you prefer, what worked, what's in progress.

**~350 tokens ambient cost.** No Docker, no API keys, no MCP servers.

```
$ uv run ~/.claude/tools/memcapture.py --stats
Sessions captured: 2347
Unique files touched: 1486
Facts by type: {'correction': 75, 'decision': 64, 'error': 361}
```

## How it works

```
  Open Claude Code ──► Work normally ──► Context compacts
       │                                        │
       │ Reads:                      PreCompact fires (automatic):
       │ • <session-memory> block       ┌──────┼──────┬──────────┐
       │   (~350 tokens, scoped         │      │      │          │
       │    to current project)   memcapture  memdigest  mempatterns
       │                         (structural) (LLM ext.) (emergent
       │                          zero-cost  ~2-5K tok)   patterns)
       │                              │         │            │
       │                              ▼         ▼            ▼
  Next session starts ◄── SessionStart ◄── ~/.claude/memory.db ─► ~/.claude/patterns/
       │                  inject: durable=global,    (SQLite)     (Obsidian wiki)
       │                  ephemeral+snapshot=per-project
       ▼
  Claude knows how you work in THIS project
```

1. **Capture** — on every context compaction, `memcapture.py` parses the JSONL transcript and extracts errors, files touched, tool usage, and session topics into SQLite
2. **Learn** — `memdigest-hook.sh` sends the last ~20% of the transcript to Claude, which extracts atomic memories: preferences, lessons, practices, and project state
3. **Inject** — at session start, ~350 tokens of learned memories are injected so Claude knows how you work

Memories are stored as atomic facts with a **topic key** — same topic always has one row, latest wins, no contradictions. Preferences persist indefinitely; project state expires in 7 days.

## Why this exists

Most Claude Code memory tools add significant ambient token cost, require external services, or install MCP servers with many tool descriptions. engram takes the best ideas and keeps it lightweight:

| Source | What we took | What we skipped |
|---|---|---|
| [claude-mem](https://github.com/thedotmack/claude-mem) | Auto-capture concept | LLM worker, Agent SDK, web viewer |
| [claude-memory-compiler](https://github.com/coleam00/claude-memory-compiler) | compile.py architecture | SessionEnd hooks, ambient injection |
| [OpenMemory](https://github.com/CaviraOSS/OpenMemory) | Temporal decay concept | Docker, MCP server, dashboard |
| [cortex](https://github.com/gambletan/cortex) | Token-budget concept | 27 MCP tools, Rust binary |

## Install

**Requirements:** [Claude Code](https://docs.anthropic.com/en/docs/claude-code), [uv](https://docs.astral.sh/uv/), [jq](https://jqlang.github.io/jq/)

```bash
git clone https://github.com/sebastianbreguel/engram.git
cd engram && ./install.sh
```

The installer copies tools, hooks, and skills to `~/.claude/`, wires hooks into `settings.json`, and runs initial capture.

```bash
# Uninstall (keeps your memory.db data)
cd engram && ./uninstall.sh
```

## Quick reference

```bash
uv run ~/.claude/tools/memcapture.py --stats            # global statistics
uv run ~/.claude/tools/memcapture.py -q "react"         # full-text search
uv run ~/.claude/tools/memcapture.py --memories          # list learned memories
uv run ~/.claude/tools/memcapture.py --forget "topic"    # delete a memory
```

## Pattern detection

engram detects emergent patterns from your session history — file pairs you always edit together, recurring errors, project streaks, and tool anomalies. Patterns are stored as an Obsidian-compatible wiki in `~/.claude/patterns/`.

```bash
uv run ~/.claude/tools/mempatterns.py --report     # show detected patterns
uv run ~/.claude/tools/mempatterns.py --status     # wiki stats
```

Use `/patterns` inside Claude Code to explore patterns and discuss skill suggestions.

**Ignoring projects:** add substrings to `~/.claude/patterns/.ignore` (one per line) to exclude projects from pattern detection. Useful for noisy repos you don't care to analyze.

## Per-project memory

When a session starts, engram injects memories scoped to where you are:

- **Durable memories** (preferences, practices) — global, appear in any project
- **Ephemeral memories** (current context, work state) — prioritized for the current project's cwd
- **Compaction snapshots** — the last work-state snapshot is injected only for the matching project

Open `vambe-datascience` and you get vambe context; switch to `engram` and you get engram context. Preferences like language and code style follow you everywhere.

## Docs

- [CLI Reference](docs/cli-reference.md) — all commands, token budget, manual install, experimental features
- [Architecture](docs/architecture.md) — file layout, SQLite schema, design principles

## License

MIT
