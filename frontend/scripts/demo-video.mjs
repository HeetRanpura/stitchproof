// Record a captioned demo walkthrough of the local app in headless Chrome, without ffmpeg.
//   node scripts/demo-video.mjs http://127.0.0.1:7862 ../docs/demo
// Frames come from the Chrome DevTools screencast; long waits (model, Gemma) are sped up;
// the frames are then re-encoded by Chrome's own MediaRecorder from a canvas.
import puppeteer from "puppeteer-core";
import { createServer } from "node:http";
import { mkdirSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { join, resolve } from "node:path";

const base = process.argv[2] ?? "http://127.0.0.1:7862";
const outDir = resolve(process.argv[3] ?? "../docs/demo");
const PHOTO = process.env.PHOTO ?? resolve("../docs/screenshots/photo_reader_photo_example.jpg");
const CHROME = process.env.CHROME ?? "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome";
const W = 1280, H = 800, SPEED = 3;
const frameDir = join(outDir, ".frames");
rmSync(frameDir, { recursive: true, force: true });
mkdirSync(frameDir, { recursive: true });

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const browser = await puppeteer.launch({ executablePath: CHROME, headless: true, args: ["--no-first-run", "--hide-scrollbars"] });
const page = await browser.newPage();
await page.setViewport({ width: W, height: H, deviceScaleFactor: 1 });
await page.emulateMediaFeatures([{ name: "prefers-color-scheme", value: "light" }]);

// --- capture -----------------------------------------------------------------
const frames = []; // {file, t}
const fast = []; // [start, end] wall-clock ms windows to speed up
const cdp = await page.createCDPSession();
cdp.on("Page.screencastFrame", async ({ data, sessionId }) => {
  const file = `f${String(frames.length).padStart(5, "0")}.jpg`;
  writeFileSync(join(frameDir, file), Buffer.from(data, "base64"));
  frames.push({ file, t: Date.now() });
  await cdp.send("Page.screencastFrameAck", { sessionId }).catch(() => {});
});

async function caption(text) {
  await page.evaluate((t) => {
    let el = document.getElementById("__demo_caption");
    if (!el) {
      el = document.createElement("div");
      el.id = "__demo_caption";
      el.style.cssText =
        "position:fixed;left:50%;bottom:28px;transform:translateX(-50%);z-index:9999;max-width:880px;padding:12px 20px;border-radius:12px;background:rgba(32,26,22,.92);color:#fbf4ea;font:500 18px/1.4 'Geist Variable',system-ui,sans-serif;box-shadow:0 12px 30px -12px rgba(0,0,0,.5);text-align:center;transition:opacity .25s";
      document.body.appendChild(el);
    }
    el.style.opacity = t ? "1" : "0";
    if (t) el.textContent = t;
  }, text);
}
const click = (sel) => page.evaluate((s) => document.querySelector(s)?.click(), sel);
const clickText = (t) =>
  page.evaluate((t) => [...document.querySelectorAll("button, a")].find((b) => b.textContent.trim().includes(t))?.click(), t);
async function fastWhile(fn) {
  const s = Date.now();
  await fn();
  fast.push([s, Date.now()]);
}

await page.goto(base, { waitUntil: "networkidle0" });
await cdp.send("Page.startScreencast", { format: "jpeg", quality: 82, maxWidth: W, maxHeight: H, everyNthFrame: 1 });
await sleep(300);

await caption("StitchProof: a tech editor for crochet patterns that runs on your computer.");
await sleep(3500);
await caption("Try the sample: a small ball with two deliberate mistakes.");
await sleep(1800);
await clickText("try a sample pattern");
await caption("A fine-tuned Qwen3.5-4B reads each row locally; plain code checks every count.");
await fastWhile(() => page.waitForFunction(() => [...document.querySelectorAll("button")].some((b) => b.textContent.includes("Edit pattern")), { timeout: 300000 }));
await caption("Two rows don't add up. Every flag shows the numbers behind it.");
await sleep(4200);
await caption("Rnd 5 says 31, but (sc 3, inc) x6 on 24 stitches makes 30.");
await sleep(3800);
await page.evaluate(() => document.querySelector('aside g[role="button"][aria-label*="Rnd 11"]')?.dispatchEvent(new MouseEvent("click", { bubbles: true })));
await caption("The silhouette traces the piece. Rnd 11 repeats 5 times instead of 6: a dent.");
await sleep(4200);

await caption("Fix Rnd 5 and check again. Unchanged rows come straight from the cache.");
await clickText("Edit pattern");
await sleep(700);
await page.evaluate(() => {
  const ta = document.querySelector("textarea");
  const v = ta.value.replace("Rnd 5: (sc 3, inc) x6 (31)", "Rnd 5: (sc 3, inc) x6 (30)");
  Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, "value").set.call(ta, v);
  ta.dispatchEvent(new Event("input", { bubbles: true }));
  const i = v.indexOf("(30)");
  ta.focus();
  ta.setSelectionRange(i, i + 4);
});
await sleep(2200);
await clickText("Check stitch counts");
await fastWhile(() => page.waitForFunction(() => [...document.querySelectorAll("button")].some((b) => b.textContent.includes("Edit pattern")), { timeout: 300000 }));
await caption("One error left: Rnd 11.");
await sleep(3000);

await click('button[aria-label="Switch to dark mode"]');
await caption("Light or dark, your choice.");
await sleep(2600);
await click('button[aria-label="Switch to light mode"]');
await sleep(800);

await caption("Printed patterns: Gemma 4 reads a photo on your computer.");
await clickText("Edit pattern");
await sleep(500);
const input = await page.$('input[type=file][accept^="image"]');
await input.uploadFile(PHOTO);
await fastWhile(() => page.waitForFunction(() => document.querySelector("figure img"), { timeout: 300000 }));
await caption("The photo sits beside the editable transcription, so you can fix any misread before checking.");
await sleep(5000);

await clickText("Stuck on a row");
await caption("Stuck mid-project? Enter your stitch count and the row.");
await sleep(2500);
await clickText("Check this row");
await fastWhile(() => page.waitForFunction(() => document.body.innerText.includes("The pattern says"), { timeout: 120000 }));
await caption("“The pattern itself doesn't add up here, so it's not you.”");
await sleep(4500);
await caption("Runs on your computer. Your pattern never leaves it.");
await sleep(3500);
await caption("");
await sleep(600);
await cdp.send("Page.stopScreencast");
await sleep(300);

// --- timing: hold each frame until the next one; slow waits play SPEED times faster ---
const inFast = (t) => fast.some(([a, b]) => t >= a && t < b);
const plan = frames.map((f, i) => {
  const next = i + 1 < frames.length ? frames[i + 1].t : f.t + 600;
  let d = next - f.t;
  if (inFast(f.t)) d /= SPEED;
  return { file: f.file, d: Math.max(16, Math.min(d, 6000)) };
});
writeFileSync(join(frameDir, "manifest.json"), JSON.stringify(plan));
const total = plan.reduce((s, p) => s + p.d, 0);
console.log(`captured ${frames.length} frames, ${(total / 1000).toFixed(1)}s after speed-up`);

// --- encode with MediaRecorder from a canvas -------------------------------------
const srv = createServer((req, res) => {
  const name = decodeURIComponent(new URL(req.url, "http://x").pathname.slice(1));
  if (name === "" || name === "index.html") {
    res.setHeader("Content-Type", "text/html");
    return res.end("<canvas id=c></canvas>");
  }
  try {
    res.setHeader("Content-Type", name.endsWith(".json") ? "application/json" : "image/jpeg");
    res.end(readFileSync(join(frameDir, name)));
  } catch {
    res.statusCode = 404;
    res.end();
  }
});
await new Promise((r) => srv.listen(0, "127.0.0.1", r));
const port = srv.address().port;
const enc = await browser.newPage();
await enc.goto(`http://127.0.0.1:${port}/`);
const result = await enc.evaluate(async (W, H) => {
  const plan = await (await fetch("/manifest.json")).json();
  const canvas = document.getElementById("c");
  canvas.width = W;
  canvas.height = H;
  const ctx = canvas.getContext("2d");
  const load = (src) => new Promise((r) => { const im = new Image(); im.onload = () => r(im); im.src = src; });
  const imgs = await Promise.all(plan.map((p) => load(p.file)));
  const types = ["video/mp4;codecs=avc1.640028", "video/mp4", "video/webm;codecs=vp9", "video/webm"];
  const mime = types.find((t) => MediaRecorder.isTypeSupported(t));
  const stream = canvas.captureStream(30);
  const rec = new MediaRecorder(stream, { mimeType: mime, videoBitsPerSecond: 1_600_000 });
  const chunks = [];
  rec.ondataavailable = (e) => e.data.size && chunks.push(e.data);
  const done = new Promise((r) => (rec.onstop = r));
  // Repaint at a steady 30 fps so still holds become real video time (a canvas stream only
  // emits frames when the canvas is painted).
  let current = imgs[0];
  ctx.drawImage(current, 0, 0, W, H);
  const ticker = setInterval(() => ctx.drawImage(current, 0, 0, W, H), 1000 / 30);
  rec.start(1000);
  const start = performance.now();
  let acc = 0;
  for (let i = 0; i < plan.length; i++) {
    current = imgs[i];
    ctx.drawImage(current, 0, 0, W, H);
    acc += plan[i].d;
    const wait = start + acc - performance.now();
    if (wait > 0) await new Promise((r) => setTimeout(r, wait));
  }
  await new Promise((r) => setTimeout(r, 400));
  clearInterval(ticker);
  rec.stop();
  await done;
  const blob = new Blob(chunks, { type: mime });
  const buf = new Uint8Array(await blob.arrayBuffer());
  let bin = "";
  for (let i = 0; i < buf.length; i += 0x8000) bin += String.fromCharCode(...buf.subarray(i, i + 0x8000));
  return { mime, b64: btoa(bin) };
}, W, H);
srv.close();
const ext = result.mime.startsWith("video/mp4") ? "mp4" : "webm";
const outFile = join(outDir, `stitchproof_demo.${ext}`);
writeFileSync(outFile, Buffer.from(result.b64, "base64"));
rmSync(frameDir, { recursive: true, force: true });
console.log(`wrote ${outFile} (${result.mime}, ${(Buffer.byteLength(result.b64, "base64") / 1e6).toFixed(1)} MB)`);
await browser.close();
