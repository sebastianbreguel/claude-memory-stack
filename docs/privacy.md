# Privacy Policy

**claude-engram** — Persistent memory for Claude Code sessions

Author: Sebastian Breguel
License: MIT
Last updated: 2026-04-14

---

## Summary

claude-engram is a 100% local plugin. All data stays on your machine. Nothing is sent to external servers.

## What is stored

claude-engram captures the following data, stored locally on disk:

- **Session metadata** — project name, git branch, topic, timestamps
- **File paths** — paths of files touched during a session (not file content)
- **Tool usage counts** — which Claude Code tools were invoked and how often
- **Error strings** — error messages encountered during sessions
- **Atomic memories** — LLM-extracted preferences, practices, and project state

All structured data is stored in `~/.claude/memory.db` (SQLite).
Pattern and context files are stored in `~/.claude/patterns/` (Markdown).

## What is NOT stored

- Full conversation transcripts
- Source code or file content
- Secrets, API keys, or values from `.env` files
- Credentials of any kind

## Network activity

claude-engram makes **zero network requests**. There is no telemetry, no analytics, no tracking, and no phoning home.

The only LLM interaction is through `claude --print` during context compaction. This runs locally through your own Claude Code session and uses whatever model and billing you already have configured. No separate API keys are required.

## Third-party services

None. claude-engram has no external dependencies, no cloud backend, and no third-party integrations.

## Data control

Your data is yours. You can:

- **Inspect** it at any time: `sqlite3 ~/.claude/memory.db` or browse `~/.claude/patterns/`
- **Delete** specific memories through the plugin's CLI tools
- **Uninstall** cleanly by running `./uninstall.sh`, which removes tools and hooks
- **Delete all data** by removing `~/.claude/memory.db` and `~/.claude/patterns/` manually

Note: `uninstall.sh` preserves `memory.db` by default so you don't lose your memories if you reinstall. Delete it manually if you want a full wipe.

## Children's privacy

claude-engram is a developer tool. It is not directed at children under 13.

## Changes to this policy

Updates will be posted in this file within the repository. No retroactive changes to data handling will be made without a new release.

## Contact

For questions about this policy, open an issue on the [GitHub repository](https://github.com/sebastianbreguel/claude-engram) or contact Sebastian Breguel directly.
