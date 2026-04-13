---
name: dream
description: "Perform a multi-phase memory consolidation pass — orienting on existing memories, gathering recent signal from logs and transcripts, merging updates into topic files, and pruning the index. Use when asked to 'dream', 'consolidate memory', 'clean up memories', 'prune memories', or 'memory maintenance'. Also trigger when memories feel stale or disorganized."
---
# Dream: Memory Consolidation

You are performing a dream — a reflective pass over your memory files. Synthesize what you've learned recently into durable, well-organized memories so that future sessions can orient quickly.

Memory directory: `${MEMORY_DIR}`
${MEMORY_DIR_CONTEXT}

Session transcripts: `${TRANSCRIPTS_DIR}` (large JSONL files — grep narrowly, don't read whole files)

---

## Phase 1 — Orient

- `ls` the memory directory to see what already exists
- Read `${INDEX_FILE}` to understand the current index
- Skim existing topic files so you improve them rather than creating duplicates
- If `logs/` or `sessions/` subdirectories exist (assistant-mode layout), review recent entries there

## Phase 2 — Gather recent signal

Look for new information worth persisting. Sources in rough priority order:

1. **Daily logs** (`logs/YYYY/MM/YYYY-MM-DD.md`) if present — these are the append-only stream
2. **Existing memories that drifted** — facts that contradict something you see in the codebase now
3. **Transcript search** — if you need specific context (e.g., "what was the error message from yesterday's build failure?"), grep the JSONL transcripts for narrow terms:
   `grep -rn "<narrow term>" ${TRANSCRIPTS_DIR}/ --include="*.jsonl" | tail -50`

Don't exhaustively read transcripts. Look only for things you already suspect matter.

## Phase 2.5 — Mine session snapshots

Scan recent PreCompact snapshots for decisions, corrections, and surprises:

```bash
ls -t ~/.claude/session-env/precompact-*.md | head -10
```

Read the 5 most recent snapshots (skip `precompact-last.md`). Look for:
- **Projects worked on** — which dirs, which branches
- **Repeated contexts** — same project appearing across multiple sessions = active work worth tracking
- **Session frequency patterns** — heavy compaction = long sessions = deep work worth capturing

Cross-reference with transcripts: if a snapshot mentions a project, grep transcripts for decisions made:
```bash
grep -rn "decided\|chose\|prefer\|convention\|pattern\|always\|never" ${TRANSCRIPTS_DIR}/ --include="*.jsonl" | tail -30
```

Extract: key decisions, user corrections, tool preferences, architecture choices.

## Phase 3 — Consolidate

For each thing worth remembering, write or update a memory file at the top level of the memory directory. Use the memory file format and type conventions from your system prompt's auto-memory section — it's the source of truth for what to save, how to structure it, and what NOT to save.

Focus on:
- Merging new signal into existing topic files rather than creating near-duplicates
- Converting relative dates ("yesterday", "last week") to absolute dates so they remain interpretable after time passes
- Deleting contradicted facts — if today's investigation disproves an old memory, fix it at the source

## Phase 4 — Prune and index

Update `${INDEX_FILE}` so it stays under ${INDEX_MAX_LINES} lines AND under ~25KB. It's an **index**, not a dump — each entry should be one line under ~150 characters: `- [Title](file.md) — one-line hook`. Never write memory content directly into it.

- Remove pointers to memories that are now stale, wrong, or superseded
- Demote verbose entries: if an index line is over ~200 chars, it's carrying content that belongs in the topic file — shorten the line, move the detail
- Add pointers to newly important memories
- Resolve contradictions — if two files disagree, fix the wrong one

## Phase 5 — Temporal review

Check for stale memories using `verified:` dates in frontmatter:

1. Scan all memory files for the `verified:` field in their frontmatter
2. If a memory has NO `verified:` field, add `verified: [today's date]` — it's being reviewed now
3. If `verified:` is older than 30 days:
   - Read the memory content
   - Check if it's still accurate against current codebase/git state
   - If still valid: update `verified:` to today
   - If outdated: fix the content or delete the file
   - If uncertain: flag it in your summary as "needs human review"

This prevents memory rot — old facts that were true once but drifted.

## Phase 5b — Concept compilation

After consolidating individual memories, look for cross-memory themes:

1. Read all memory files in the current project
2. Identify recurring concepts (technologies, patterns, preferences that appear in 2+ files)
3. If `~/.claude/compiled-knowledge/` exists, read `concepts.md` and update it
4. If it doesn't exist, note the themes in your summary for potential future compilation

Don't create the compiled-knowledge directory — that's memcompile.py's job. Just report what you see.

---

Return a brief summary of what you consolidated, updated, or pruned. If nothing changed (memories are already tight), say so.${ADDITIONAL_CONTEXT?`

## Additional context

${ADDITIONAL_CONTEXT}`:""}
