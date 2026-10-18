// Render docs/thumbnail/thumbnail.html to a 1280x720 PNG (YouTube thumbnail size).
//   node scripts/thumbnail.mjs
import puppeteer from "puppeteer-core";
import { resolve } from "node:path";
import { statSync } from "node:fs";
const html = resolve("../docs/thumbnail/thumbnail.html");
const out = resolve("../docs/thumbnail/stitchproof_thumbnail.png");
const b = await puppeteer.launch({ executablePath: "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome", headless: true, args: ["--allow-file-access-from-files"] });
const p = await b.newPage();
await p.setViewport({ width: 1280, height: 720, deviceScaleFactor: 1 });
await p.goto(`file://${html}`, { waitUntil: "networkidle0" });
await p.evaluate(() => document.fonts.ready);
await p.screenshot({ path: out, type: "png" });
await b.close();
console.log(`wrote ${out} (${(statSync(out).size / 1024).toFixed(0)} KB)`);
