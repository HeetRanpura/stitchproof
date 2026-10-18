// Drive the local app in headless Chrome and save screenshots of each state.
//   node scripts/shots.mjs http://127.0.0.1:7861 ../docs/screenshots [scene,...]
// Uses the installed Google Chrome with a throwaway profile; never touches the user's browser data.
import puppeteer from "puppeteer-core";
import { mkdirSync } from "node:fs";
import { resolve } from "node:path";

const base = process.argv[2] ?? "http://127.0.0.1:7861";
const out = resolve(process.argv[3] ?? "../docs/screenshots");
const only = process.argv[4]?.split(",");
const photo = process.env.PHOTO;
mkdirSync(out, { recursive: true });

const CHROME = process.env.CHROME ?? "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome";
const browser = await puppeteer.launch({ executablePath: CHROME, headless: true, args: ["--no-first-run", "--no-default-browser-check"] });
const log = (...a) => console.log(...a);

async function page({ width = 1440, height = 960, dark = false, mobile = false } = {}) {
  const p = await browser.newPage();
  await p.setViewport({ width, height, deviceScaleFactor: 2, isMobile: mobile, hasTouch: mobile });
  await p.emulateMediaFeatures([{ name: "prefers-color-scheme", value: dark ? "dark" : "light" }]);
  const external = [];
  p.on("request", (r) => {
    const u = new URL(r.url());
    if (!["127.0.0.1", "localhost"].includes(u.hostname) && !u.protocol.startsWith("data") && !u.protocol.startsWith("blob")) external.push(r.url());
  });
  p.external = external;
  p.on("pageerror", (e) => log("PAGE ERROR", e.message));
  p.on("console", (m) => m.type() === "error" && log("CONSOLE", m.text()));
  await p.goto(base, { waitUntil: "networkidle0" });
  return p;
}

async function clickText(p, text) {
  const ok = await p.evaluate((t) => {
    const el = [...document.querySelectorAll("button, a")].find((b) => b.textContent.trim().includes(t));
    if (el) el.click();
    return !!el;
  }, text);
  if (!ok) throw new Error(`no button with text: ${text}`);
}

async function waitDone(p, timeout = 240000) {
  await p.waitForFunction(() => [...document.querySelectorAll("button")].some((b) => b.textContent.includes("Edit pattern")), { timeout });
  await new Promise((r) => setTimeout(r, 600));
}

const scenes = {
  async empty() {
    const p = await page();
    await p.screenshot({ path: `${out}/app_empty.png` });
    log("empty: external requests", p.external);
  },
  async review() {
    const p = await page({ height: 1180 });
    await clickText(p, "try a sample pattern");
    await waitDone(p);
    await p.screenshot({ path: `${out}/app_review.png` });
    // select Rnd 11 via the flagged list
    await p.evaluate(() => [...document.querySelectorAll("aside button")].find((b) => b.textContent.includes("Rnd 11"))?.click());
    await new Promise((r) => setTimeout(r, 500));
    await p.screenshot({ path: `${out}/app_review_rnd11.png` });
    log("review: external requests", p.external);
  },
  async dark() {
    const p = await page({ height: 1180, dark: true });
    await clickText(p, "try a sample pattern");
    await waitDone(p);
    await p.screenshot({ path: `${out}/app_review_dark.png` });
  },
  async mobile() {
    const p = await page({ width: 390, height: 844, mobile: true });
    await p.screenshot({ path: `${out}/app_mobile_empty.png` });
    await clickText(p, "try a sample pattern");
    await waitDone(p);
    const overflow = await p.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
    log("mobile horizontal overflow px:", overflow);
    await p.screenshot({ path: `${out}/app_mobile_review.png`, fullPage: true });
  },
  async maker() {
    const p = await page({ height: 760 });
    await clickText(p, "Stuck on a row");
    await clickText(p, "Check this row");
    await p.waitForFunction(() => document.body.innerText.includes("The pattern says"), { timeout: 120000 });
    await new Promise((r) => setTimeout(r, 500));
    await p.screenshot({ path: `${out}/app_maker.png` });
  },
  async theme() {
    const p = await page({ height: 900 });
    const bg = () => p.evaluate(() => getComputedStyle(document.body).backgroundColor);
    const before = await bg();
    await p.evaluate(() => document.querySelector('button[aria-label="Switch to dark mode"]').click());
    await new Promise((r) => setTimeout(r, 300));
    const after = await bg();
    await p.reload({ waitUntil: "networkidle0" });
    const reloaded = await bg();
    const label = await p.evaluate(() => document.querySelector('button[aria-label$="mode"]').getAttribute("aria-label"));
    log(`theme: light ${before} -> dark ${after}; after reload ${reloaded}; button now "${label}"`);
    if (after === before || reloaded !== after) throw new Error("toggle did not switch or persist");
    await p.screenshot({ path: `${out}/app_empty_dark.png` });
  },
  async photo() {
    if (!photo) return log("photo: set PHOTO=/path/to/image.jpg");
    const p = await page({ height: 1100 });
    await clickText(p, "Paste the text");
    const input = await p.$('input[type=file][accept^="image"]');
    await input.uploadFile(photo);
    await p.waitForFunction(() => document.querySelector("figure img"), { timeout: 300000 });
    await new Promise((r) => setTimeout(r, 800));
    await p.screenshot({ path: `${out}/app_photo_review.png` });
  },
};

for (const [name, fn] of Object.entries(scenes)) {
  if (only && !only.includes(name)) continue;
  const t = Date.now();
  try {
    await fn();
    log(`${name}: ok (${((Date.now() - t) / 1000).toFixed(1)}s)`);
  } catch (e) {
    log(`${name}: FAILED ${e.message}`);
  }
}
await browser.close();
