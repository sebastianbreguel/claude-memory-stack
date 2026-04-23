# claude-engram — demo animations

Five HyperFrames-ready compositions (1920×800, 30fps, GSAP) that showcase the core engram features. Each is a standalone `.html` file with a `data-composition-id` for the HyperFrames renderer and a built-in fallback preview mode.

## Preview locally

Any of the files works directly in a browser — no build step, no server needed:

```bash
open demo/session-flow.html        # or any other .html
```

Preview behavior (when viewport ≠ 1920×800):
- Auto-scales and centers the 1920×800 stage to fit the window.
- Auto-replays the timeline on page load.
- **Click anywhere** to replay.
- **Resize** the window to re-fit.

At exact 1920×800 (the render target), the stage locks and plays once — that's the HyperFrames capture path.

## Render to video (HyperFrames)

Each stage carries `data-composition-id`, `data-width`, `data-height`, `data-duration`, `data-fps`. Clips inside expose `data-start`, `data-duration`, `data-track-index` so the renderer can assemble tracks without parsing the GSAP timeline. Point your HyperFrames pipeline at the file — no extra config.

## The five beats

| file | duration | composition id | what it shows | engram feature |
|---|---|---|---|---|
| `session-flow.html` | 11s | `engram-session-flow` | Session 1 → "2 hours later…" → Session 2 loads with the `last:` bullet pulsing to show continuity | 3-bullet executive injected at SessionStart |
| `globals-beat.html` | 5s | `engram-globals-beat` | SessionStart banner with "196 memories" callout exposing USER / FEEDBACK / PROJECT / REFERENCE entries | Global auto-memory, 4 memory types |
| `patterns-beat.html` | 5s | `engram-patterns-beat` | Banner + memdoctor panel firing `rapid-corrections` and `restart-cluster` signals, suggesting `/debug` | memdoctor signals (correction-heavy, rapid-corrections, restart-cluster, error-loop, keep-going-loop) |
| `precompact-beat.html` | 6s | `engram-precompact-beat` | Conversation hits 93% context → `PreCompact:compact intercepted` → executive saved to `~/.claude/engram/executive/claude-engram.md` | PreCompact hook, per-cwd executive cache |
| `scale-beat.html` | 5s | `engram-scale-beat` | 3-panel realistic chrome showing scale/usage story | (scale narrative) |

## Recommended use order

For a cold-pitch walkthrough (landing page, README, or video reel), play in this order:

1. **`session-flow.html`** — the problem + payoff (Claude remembers where you left off).
2. **`precompact-beat.html`** — the rescue moment (context saved before compaction wipes it).
3. **`globals-beat.html`** — the cross-project angle (memories travel with you).
4. **`patterns-beat.html`** — the intelligence layer (memdoctor catches you when you're spiraling).
5. **`scale-beat.html`** — the "this works at scale" close.

Each beat is designed to stand alone, so you can also drop a single one into a tweet, a docs section, or a slide.

## Editing tips

- Colors live in `:root { --bg, --fg, --accent, ... }` at the top of every file — tweak once.
- Timeline offsets are plain numbers on `tl.fromTo(... , N)` calls; search for the seconds and shift.
- Numbers shown in banners (sessions, memories) are hard-coded for the demo — keep them internally consistent across beats (globals shows 49/196, patterns shows 50/197 one session later).
- Paths and signal names should track the real code — if you rename `rapid-corrections` or move the executive cache, update the HTMLs too.
