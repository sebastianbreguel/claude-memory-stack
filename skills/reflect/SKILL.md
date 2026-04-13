---
name: reflect
description: "Analyze recent session snapshots and memory files to detect behavioral patterns, then propose advisory updates to CLAUDE.md. Use when asked to 'reflect', 'find patterns', 'what have I been doing', 'update my rules', or after accumulating 5+ sessions. ADVISORY ONLY — never writes to CLAUDE.md without explicit approval."
---
# Reflect: Advisory Pattern Detection

You are performing a reflection — analyzing recent sessions and memories to detect recurring patterns, preferences, anti-patterns, and useful rules. Your output is ADVISORY: you propose changes, the user decides what to keep.

Memory directory: `${MEMORY_DIR}`
${MEMORY_DIR_CONTEXT}

Session snapshots: `~/.claude/session-env/`
Compiled knowledge (if exists): `~/.claude/compiled-knowledge/`

---

## Phase 1 — Gather Signal

### 1a. Read recent session snapshots
```bash
ls -t ~/.claude/session-env/precompact-*.md | head -10
```
Read the 5 most recent snapshots (skip `precompact-last.md` which is a duplicate of the latest). Extract:
- What projects were being worked on
- What git branches were active
- What triggers caused compaction

### 1b. Read current memories
- Read `${INDEX_FILE}` and all memory files it references
- Note the `type:` of each memory (user, feedback, project, reference)

### 1c. Read current CLAUDE.md
- Read the CLAUDE.md for the current project (`.claude/CLAUDE.md` or project-level)
- Read the global `~/.claude/CLAUDE.md`
- Note all existing rules — you will check for violations and gaps

### 1d. Read compiled knowledge (if exists)
- If `~/.claude/compiled-knowledge/concepts.md` exists, read it for cross-project context

---

## Phase 2 — Detect Patterns

Analyze the gathered signal across 6 categories:

### Category 1: Persistent Preferences
Things the user does repeatedly without being told. Look for:
- Tool choices (which tools are used most/least)
- Language preferences (Spanish vs English in different contexts)
- Code style patterns not captured in CLAUDE.md

### Category 2: Design Decisions That Worked
Approaches that were chosen and not reverted:
- Architecture choices
- Library/tool selections
- Workflow patterns

### Category 3: Anti-Patterns to Avoid
Things that went wrong or were corrected:
- Approaches that were tried and abandoned
- Corrections the user made ("no, not that way")
- Patterns that caused errors or rework

### Category 4: Efficiency Lessons
Process improvements discovered:
- Shortcuts found
- Unnecessary steps eliminated
- Better tool combinations

### Category 5: Project-Specific Patterns
Patterns that recur within a specific project:
- Naming conventions
- File organization habits
- Testing preferences

### Category 6: Rule Violations (HIGHEST PRIORITY)
**Check every existing CLAUDE.md rule against recent sessions:**
- Was any rule violated? → Strengthen it with context
- Was any rule followed unusually well? → Note as validated
- Are there rules that no longer apply? → Suggest removal

---

## Phase 3 — Score Patterns

For each detected pattern:
- **Frequency**: How many sessions show this pattern?
  - 1 occurrence = one-off (ignore)
  - 2 occurrences = emerging pattern (note)
  - 3+ occurrences = strong pattern (recommend)
- **Consistency**: Is the pattern contradicted in any session?
- **Scope**: Is it global or project-specific?

Only propose rules for patterns with 2+ occurrences.

---

## Phase 4 — Propose Updates

Present findings as a structured report:

### Format
```markdown
## Reflection Report — [date]

### Strong Patterns (3+ occurrences)
1. [Pattern description]
   - Evidence: [which sessions/memories]
   - Proposed CLAUDE.md rule: `[one-line imperative rule]`

### Emerging Patterns (2 occurrences)
1. [Pattern description]
   - Evidence: [which sessions/memories]
   - Proposed CLAUDE.md rule: `[one-line imperative rule]`

### Rule Violations Detected
1. [Rule] was violated in [session/context]
   - Suggested strengthening: [how to make it clearer]

### Stale Rules (consider removing)
1. [Rule] — not relevant in recent sessions because [reason]

### Memory Health
- Memories that may be outdated: [list]
- Memories that should be merged: [list]
- Missing memories (gaps in coverage): [list]
```

---

## CRITICAL RULES

1. **NEVER write to CLAUDE.md directly.** Present proposals and wait for explicit approval.
2. **NEVER create memories.** Only propose what should be remembered.
3. **Proposed rules must be one-line, imperative tone.** No verbose explanations in CLAUDE.md.
4. **Distinguish global vs project-scoped.** A React pattern does not belong in global CLAUDE.md.
5. **Be conservative.** When in doubt, report the pattern but don't propose a rule.
6. **Credit your evidence.** Every proposal must cite which sessions or memories support it.
