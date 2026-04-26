#!/usr/bin/env node
import { spawn } from "node:child_process";
import { existsSync } from "node:fs";
import { mkdir, readFile, rm, writeFile } from "node:fs/promises";
import path from "node:path";
import { setTimeout as delay } from "node:timers/promises";

const root = path.resolve(path.dirname(new URL(import.meta.url).pathname), "..");
const chromePath =
  process.env.CHROME_PATH || "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome";
const userDataDir = process.env.CHROME_USER_DATA_DIR || "/tmp/claude-engram-render-chrome";
const frameRoot = process.env.FRAME_DIR || "/tmp/claude-engram-demo-frames";
const viewport = { width: 1920, height: 800 };
const gifSize = { width: 1280, height: 533 };
const fps = Number(process.env.FPS || 20);

const presets = new Map([
  ["readme-hero-focus", ["demo/readme-hero-focus.html", "demo/readme-hero-focus.gif", "readme-hero-focus"]],
  ["readme-hero-split", ["demo/readme-hero-split.html", "demo/readme-hero-split.gif", "readme-hero-split"]],
  ["readme-hero-install", ["demo/readme-hero-install.html", "demo/readme-hero-install.gif", "readme-hero-install"]],
  ["engram-hero", ["demo/engram-hero.html", "demo/engram-hero.gif", "engram-hero"]],
  ["scale-beat", ["demo/scale-beat.html", "demo/scale-beat.gif", "engram-scale-beat"]],
  ["session-flow", ["demo/session-flow.html", "demo/session-flow.gif", "engram-session-flow"]],
]);

const names = process.argv.slice(2);
const selected = (names.length ? names : [...presets.keys()]).map((name) => {
  if (!presets.has(name)) {
    throw new Error(`Unknown demo "${name}". Known demos: ${[...presets.keys()].join(", ")}`);
  }
  const [html, gif, id] = presets.get(name);
  return { name, html, gif, id };
});

class CDP {
  constructor(url) {
    this.ws = new WebSocket(url);
    this.nextId = 1;
    this.pending = new Map();
    this.listeners = new Map();
    this.ready = new Promise((resolve, reject) => {
      this.ws.addEventListener("open", resolve, { once: true });
      this.ws.addEventListener("error", reject, { once: true });
    });
    this.ws.addEventListener("message", (event) => {
      const msg = JSON.parse(event.data);
      if (msg.id && this.pending.has(msg.id)) {
        const { resolve, reject } = this.pending.get(msg.id);
        this.pending.delete(msg.id);
        if (msg.error) reject(new Error(`${msg.error.message}: ${msg.error.data || ""}`));
        else resolve(msg.result);
        return;
      }
      if (msg.method && this.listeners.has(msg.method)) {
        for (const listener of this.listeners.get(msg.method)) listener(msg.params || {});
      }
    });
  }

  async send(method, params = {}) {
    await this.ready;
    const id = this.nextId++;
    const promise = new Promise((resolve, reject) => this.pending.set(id, { resolve, reject }));
    this.ws.send(JSON.stringify({ id, method, params }));
    return promise;
  }

  waitFor(method, timeoutMs = 15000) {
    return new Promise((resolve, reject) => {
      const timer = setTimeout(() => {
        const set = this.listeners.get(method);
        if (set) set.delete(handler);
        reject(new Error(`Timed out waiting for ${method}`));
      }, timeoutMs);
      const handler = (params) => {
        clearTimeout(timer);
        const set = this.listeners.get(method);
        if (set) set.delete(handler);
        resolve(params);
      };
      if (!this.listeners.has(method)) this.listeners.set(method, new Set());
      this.listeners.get(method).add(handler);
    });
  }

  close() {
    this.ws.close();
  }
}

async function waitForDevToolsPort() {
  const portFile = path.join(userDataDir, "DevToolsActivePort");
  for (let i = 0; i < 120; i++) {
    if (existsSync(portFile)) {
      const text = await readFile(portFile, "utf8");
      return text.trim().split("\n")[0];
    }
    await delay(100);
  }
  throw new Error("Chrome did not expose DevToolsActivePort");
}

async function newPage(port) {
  const res = await fetch(`http://127.0.0.1:${port}/json/new?about:blank`, { method: "PUT" });
  if (!res.ok) throw new Error(`Could not create Chrome target: ${res.status} ${await res.text()}`);
  const target = await res.json();
  return new CDP(target.webSocketDebuggerUrl);
}

async function waitForTimeline(client, timelineId) {
  const expression = `Boolean(window.gsap && window.__timelines && window.__timelines[${JSON.stringify(timelineId)}])`;
  for (let i = 0; i < 120; i++) {
    const result = await client.send("Runtime.evaluate", { expression, returnByValue: true });
    if (result.result?.value === true) return;
    await delay(100);
  }
  throw new Error(`Timeline ${timelineId} was not available`);
}

async function captureDemo(port, demo) {
  const htmlPath = path.join(root, demo.html);
  const html = await readFile(htmlPath, "utf8");
  const durationMatch = html.match(/data-duration="([0-9.]+)"/);
  if (!durationMatch) throw new Error(`No data-duration found in ${demo.html}`);

  const duration = Number(durationMatch[1]);
  const totalFrames = Math.ceil((duration + 1) * fps);
  const frameDir = path.join(frameRoot, demo.name);
  await rm(frameDir, { recursive: true, force: true });
  await mkdir(frameDir, { recursive: true });

  const client = await newPage(port);
  await client.send("Page.enable");
  await client.send("Runtime.enable");
  await client.send("Emulation.setDeviceMetricsOverride", {
    width: viewport.width,
    height: viewport.height,
    deviceScaleFactor: 1,
    mobile: false,
    screenWidth: viewport.width,
    screenHeight: viewport.height,
  });

  const loaded = client.waitFor("Page.loadEventFired", 30000);
  await client.send("Page.navigate", { url: `file://${htmlPath}` });
  await loaded;
  await waitForTimeline(client, demo.id);

  console.log(`capture ${demo.gif}: ${totalFrames} frames @ ${fps}fps`);
  for (let i = 0; i < totalFrames; i++) {
    const t = Math.min(i / fps, duration - 0.01);
    await client.send("Runtime.evaluate", {
      expression: `(() => { const tl = window.__timelines[${JSON.stringify(demo.id)}]; tl.pause(${t.toFixed(4)}, false); return tl.time(); })()`,
      returnByValue: true,
    });
    await delay(8);
    const shot = await client.send("Page.captureScreenshot", {
      format: "png",
      fromSurface: true,
      captureBeyondViewport: false,
    });
    await writeFile(path.join(frameDir, `frame_${String(i).padStart(4, "0")}.png`), Buffer.from(shot.data, "base64"));
  }
  client.close();
  return frameDir;
}

function run(cmd, args) {
  return new Promise((resolve, reject) => {
    const child = spawn(cmd, args, { stdio: ["ignore", "pipe", "pipe"] });
    let stderr = "";
    child.stdout.on("data", (chunk) => process.stdout.write(chunk));
    child.stderr.on("data", (chunk) => {
      stderr += chunk.toString();
    });
    child.on("close", (code) => {
      if (code === 0) resolve();
      else reject(new Error(`${cmd} ${args.join(" ")} failed with code ${code}\n${stderr}`));
    });
  });
}

async function encodeGif(demo, frameDir) {
  const palette = path.join(frameDir, "palette.png");
  const input = path.join(frameDir, "frame_%04d.png");
  const output = path.join(root, demo.gif);
  const scale = `scale=${gifSize.width}:${gifSize.height}:flags=lanczos,fps=${fps}`;
  await run("ffmpeg", ["-y", "-v", "error", "-framerate", String(fps), "-i", input, "-vf", `${scale},palettegen=stats_mode=diff`, palette]);
  await run("ffmpeg", ["-y", "-v", "error", "-framerate", String(fps), "-i", input, "-i", palette, "-lavfi", `${scale}[x];[x][1:v]paletteuse=dither=bayer:bayer_scale=3`, output]);
}

await rm(userDataDir, { recursive: true, force: true });
await rm(frameRoot, { recursive: true, force: true });
await mkdir(userDataDir, { recursive: true });

const chrome = spawn(chromePath, [
  "--headless=new",
  "--disable-gpu",
  "--no-first-run",
  "--no-default-browser-check",
  "--disable-background-networking",
  `--user-data-dir=${userDataDir}`,
  "--remote-debugging-port=0",
  `--window-size=${viewport.width},${viewport.height}`,
  "about:blank",
], { stdio: ["ignore", "ignore", "ignore"] });

try {
  const port = await waitForDevToolsPort();
  for (const demo of selected) {
    const frameDir = await captureDemo(port, demo);
    await encodeGif(demo, frameDir);
    console.log(`wrote ${demo.gif}`);
  }
} finally {
  chrome.kill("SIGTERM");
  await delay(500);
}
