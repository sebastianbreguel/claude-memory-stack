# Claude-engram

**Claude forgets everything between sessions.** Your preferences, your project state, where you left off — gone the moment you close the terminal.

claude-engram fixes that. **~350 ambient tokens. No Docker, no API keys, no MCP.**

## What you see

When you open Claude Code, claude-engram injects a short note from your last session:

```
Learned preferences & practices:
- User prefers uv, never pip — responds in Spanish
- Terse responses, no docstrings unless asked

Current context:
- Was refactoring auth to JWT; signup still on old sessions
- Next: wire signup to JWT flow
```

Claude picks up where you left off. No re-explaining.

## How it works

claude-engram has two jobs: **remember** and **inject**.

1. **On compaction** — one background LLM pass reads your session and extracts atomic memories: preferences, project state, and a handoff paragraph. Stored in local SQLite, keyed by topic (same topic = one row, latest wins, no contradictions).
2. **On session start** — ~350 tokens of what matters are injected, scoped to your current project. Preferences follow you everywhere; project state stays local and expires in 7 days.

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
- **LLM calls**: one `claude --print` pass on compaction (~2-5K tokens, local to your session). No external API calls.
- **Uninstall**: `./uninstall.sh` removes tools and hooks. Your data is preserved unless you delete it.

## CLI

```bash
uv run ~/.claude/tools/engram.py stats              # what claude-engram knows
uv run ~/.claude/tools/engram.py memories           # list learned memories
uv run ~/.claude/tools/engram.py forget "topic"     # delete a memory
uv run ~/.claude/tools/engram.py patterns --report  # detected patterns
```

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

## At a glance

![claude-engram — session memory for Claude Code](docs/claude-engram-explainer.svg)

## Docs

- [CLI Reference](docs/cli-reference.md) — all commands, token budget, manual install, experimental features
- [Architecture](docs/architecture.md) — file layout, SQLite schema, design principles
- [Privacy Policy](docs/privacy.md) — what's captured, what's not, zero network activity

## License

MIT
