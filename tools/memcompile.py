#!/usr/bin/env python3
"""memcompile — Cross-project memory compilation and health checks.

Inspired by coleam00/claude-memory-compiler's compile.py + lint.py.
Walks all Claude Code project memory directories, parses memory files,
and generates compiled knowledge (concepts, connections, health report).

Usage:
    uv run ~/.claude/tools/memcompile.py              # full compile
    uv run ~/.claude/tools/memcompile.py --lint-only   # health checks only
    uv run ~/.claude/tools/memcompile.py --dry-run     # show what would compile
"""
# /// script
# requires-python = ">=3.11"
# dependencies = ["anthropic"]
# ///

from __future__ import annotations

import argparse
import re
from datetime import datetime, timedelta
from pathlib import Path

PROJECTS_DIR = Path.home() / ".claude" / "projects"
OUTPUT_DIR = Path.home() / ".claude" / "compiled-knowledge"
STALE_DAYS = 30


def parse_frontmatter(path: Path) -> dict[str, str]:
    """Extract YAML-like frontmatter from a memory file."""
    text = path.read_text(encoding="utf-8")
    match = re.match(r"^---\n(.*?)\n---", text, re.DOTALL)
    if not match:
        return {"body": text, "_path": str(path)}
    fm: dict[str, str] = {"_path": str(path)}
    for line in match.group(1).splitlines():
        if ":" in line:
            key, _, val = line.partition(":")
            fm[key.strip()] = val.strip()
    fm["body"] = text[match.end() :].strip()
    return fm


def collect_memories() -> list[dict[str, str]]:
    """Walk all project memory dirs and parse every .md file."""
    memories: list[dict[str, str]] = []
    if not PROJECTS_DIR.exists():
        return memories
    for project_dir in sorted(PROJECTS_DIR.iterdir()):
        mem_dir = project_dir / "memory"
        if not mem_dir.is_dir():
            continue
        for md_file in sorted(mem_dir.glob("*.md")):
            if md_file.name == "MEMORY.md":
                continue
            fm = parse_frontmatter(md_file)
            fm["_project"] = project_dir.name
            memories.append(fm)
    return memories


def lint_memories(memories: list[dict[str, str]]) -> str:
    """Run health checks on collected memories."""
    lines: list[str] = [
        "# Memory Health Report",
        f"**Generated:** {datetime.now():%Y-%m-%d %H:%M}",
        "",
    ]

    # Check 1: Stale memories (no verified date or >30 days old)
    stale: list[str] = []
    cutoff = datetime.now() - timedelta(days=STALE_DAYS)
    for m in memories:
        verified = m.get("verified", "")
        if not verified:
            stale.append(f"- `{m['_path']}` — no `verified:` date")
        else:
            try:
                vdate = datetime.strptime(verified, "%Y-%m-%d")
                if vdate < cutoff:
                    stale.append(
                        f"- `{m['_path']}` — verified {verified} ({STALE_DAYS}+ days ago)"
                    )
            except ValueError:
                stale.append(f"- `{m['_path']}` — invalid verified date: {verified}")

    lines.append(f"## Stale Memories ({len(stale)})")
    lines.extend(stale if stale else ["- None"])
    lines.append("")

    # Check 2: Missing type field
    no_type = [f"- `{m['_path']}`" for m in memories if not m.get("type")]
    lines.append(f"## Missing Type ({len(no_type)})")
    lines.extend(no_type if no_type else ["- None"])
    lines.append("")

    # Check 3: Duplicate names across projects
    name_map: dict[str, list[str]] = {}
    for m in memories:
        name = m.get("name", m.get("_path", ""))
        name_map.setdefault(name, []).append(m.get("_project", "?"))
    dupes = {k: v for k, v in name_map.items() if len(v) > 1}
    lines.append(f"## Potential Duplicates ({len(dupes)})")
    for name, projects in dupes.items():
        lines.append(f"- `{name}` appears in: {', '.join(projects)}")
    if not dupes:
        lines.append("- None")
    lines.append("")

    # Check 4: Large memories (body > 2000 chars)
    large = [
        f"- `{m['_path']}` ({len(m.get('body', '')):,} chars)"
        for m in memories
        if len(m.get("body", "")) > 2000
    ]
    lines.append(f"## Oversized Memories ({len(large)})")
    lines.extend(large if large else ["- None"])
    lines.append("")

    # Check 5: Empty memories
    empty = [
        f"- `{m['_path']}`" for m in memories if len(m.get("body", "").strip()) < 10
    ]
    lines.append(f"## Empty/Near-Empty ({len(empty)})")
    lines.extend(empty if empty else ["- None"])
    lines.append("")

    # Summary
    projects_with_mem = len({m["_project"] for m in memories})
    by_type: dict[str, int] = {}
    for m in memories:
        t = m.get("type", "unknown")
        by_type[t] = by_type.get(t, 0) + 1
    lines.append("## Summary")
    lines.append(
        f"- **{len(memories)}** memory files across **{projects_with_mem}** projects"
    )
    lines.append(
        f"- By type: {', '.join(f'{t}: {c}' for t, c in sorted(by_type.items()))}"
    )
    lines.append(
        f"- Stale: {len(stale)} | No type: {len(no_type)} | Dupes: {len(dupes)} | Large: {len(large)} | Empty: {len(empty)}"
    )

    return "\n".join(lines)


def compile_concepts(memories: list[dict[str, str]]) -> str:
    """Use Claude to extract cross-project concepts from memories."""
    import anthropic

    client = anthropic.Anthropic()

    memory_text = "\n\n---\n\n".join(
        f"**Project:** {m.get('_project', '?')} | **Type:** {m.get('type', '?')} | **Name:** {m.get('name', '?')}\n{m.get('body', '')}"
        for m in memories
    )

    response = client.messages.create(
        model="claude-sonnet-4-5",
        max_tokens=4096,
        messages=[
            {
                "role": "user",
                "content": f"""Analyze these memory files from multiple Claude Code projects. Extract:

1. **Concepts** — recurring themes, technologies, patterns, preferences that appear across 2+ projects
2. **Connections** — relationships between projects (shared tech, similar patterns, dependencies)

Format as markdown with two sections. Be concise — one line per concept/connection. Only include things that appear in multiple projects or are clearly important decisions.

<memories>
{memory_text}
</memories>""",
            }
        ],
    )

    return f"# Compiled Knowledge\n**Generated:** {datetime.now():%Y-%m-%d %H:%M}\n\n{response.content[0].text}"


def main() -> None:
    parser = argparse.ArgumentParser(description="Cross-project memory compiler")
    parser.add_argument(
        "--lint-only", action="store_true", help="Only run health checks"
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Show what would be compiled"
    )
    args = parser.parse_args()

    memories = collect_memories()
    print(
        f"Found {len(memories)} memory files across {len({m['_project'] for m in memories})} projects"
    )

    if args.dry_run:
        for m in memories:
            print(
                f"  {m.get('_project', '?'):40s} {m.get('type', '?'):12s} {m.get('name', '?')}"
            )
        return

    # Always run lint
    health = lint_memories(memories)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUTPUT_DIR / "health.md").write_text(health, encoding="utf-8")
    print(f"Health report → {OUTPUT_DIR / 'health.md'}")

    if args.lint_only:
        print(health)
        return

    if len(memories) < 3:
        print("Too few memories for meaningful compilation. Run --lint-only instead.")
        return

    # Compile concepts via LLM
    print("Compiling concepts via Claude...")
    compiled = compile_concepts(memories)
    (OUTPUT_DIR / "concepts.md").write_text(compiled, encoding="utf-8")
    print(f"Concepts → {OUTPUT_DIR / 'concepts.md'}")
    print("Done.")


if __name__ == "__main__":
    main()
