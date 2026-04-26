# claude-engram — demo animations

Six HyperFrames-ready compositions (1920×800, 30fps, GSAP) that showcase claude-engram from different angles. Each is a standalone `.html` file with a `data-composition-id` for the HyperFrames renderer and a built-in fallback preview mode.

## README hero proposals

| file | duration | output | best use |
|---|---:|---|---|
| `readme-hero-focus.html` | 9s | `readme-hero-focus.gif` | **Selected for README.** Fastest "warm start" payoff in a single terminal. |
| `readme-hero-split.html` | 10s | `readme-hero-split.gif` | Strong before/after comparison: fresh shell with and without engram. |
| `readme-hero-install.html` | 9s | `readme-hero-install.gif` | Install-first pitch for launch posts or docs sections. |

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

## Render GIFs

The repo includes a local renderer for README GIF assets. It follows the HyperFrames quickstart requirements: Node.js 22+, FFmpeg, and a browser capture path.

```bash
node demo/render-gifs.mjs readme-hero-focus readme-hero-split readme-hero-install
```

Set `CHROME_PATH` if Chrome is not at `/Applications/Google Chrome.app/Contents/MacOS/Google Chrome`.

## Existing beats

| file | duration | composition id | what it shows | engram feature |
|---|---|---|---|---|
| `readme-hero-focus.html` | 9s | `readme-hero-focus` | Single-terminal warm start: SessionStart injects status, last, next, then answers "where were we?" | README conversion hero |
| `readme-hero-split.html` | 10s | `readme-hero-split` | Side-by-side fresh shell: no context vs claude-engram handoff | Before/after proof |
| `readme-hero-install.html` | 9s | `readme-hero-install` | Install message plus next-launch terminal showing immediate context | Launch / install pitch |
| `engram-hero.html` | 23s | `engram-hero` | Longer narrative: day 1 capture, next-day split, close card | Full story hero |
| `session-flow.html` | 11s | `engram-session-flow` | Session 1 → "2 hours later…" → Session 2 loads with the `last:` bullet pulsing to show continuity | 3-bullet executive injected at SessionStart |
| `scale-beat.html` | 10s | `engram-scale-beat` | 3-panel realistic chrome showing per-project memory at scale | Scale narrative |

## Recommended use order

For a cold-pitch walkthrough (landing page, README, or video reel), play in this order:

1. **`readme-hero-focus.html`** — the first README impression.
2. **`readme-hero-split.html`** — the clearest before/after proof.
3. **`session-flow.html`** — the mechanical flow behind the payoff.
4. **`scale-beat.html`** — the "this works across projects" close.

Each beat is designed to stand alone, so you can also drop a single one into a tweet, a docs section, or a slide.

## Editing tips

- Colors live in `:root { --bg, --fg, --accent, ... }` at the top of every file — tweak once.
- Timeline offsets are plain numbers on `tl.fromTo(... , N)` calls; search for the seconds and shift.
- Numbers shown in banners (sessions, memories) are hard-coded for the demo — keep them internally consistent across beats (globals shows 49/196, patterns shows 50/197 one session later).
- Paths and signal names should track the real code — if you rename `rapid-corrections` or move the executive cache, update the HTMLs too.
