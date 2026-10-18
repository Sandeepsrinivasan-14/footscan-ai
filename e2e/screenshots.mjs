// Regenerates docs/screenshots/*.jpg from a running `python scripts/e2e_server.py` (fake model,
// synthetic images). Usage:  node screenshots.mjs [baseUrl]
import path from "node:path";
import { fileURLToPath } from "node:url";
import { chromium } from "@playwright/test";

const base = process.argv[2] || "http://127.0.0.1:8791";
const here = path.dirname(fileURLToPath(import.meta.url));
const fixture = (n) => path.join(here, "fixtures", n);
const out = (n) => path.join(here, "..", "docs", "screenshots", n);
const shot = { type: "jpeg", quality: 82 };

const browser = await chromium.launch({ executablePath: process.env.E2E_CHROMIUM || undefined });

async function open(theme, viewport, extra = {}) {
  const ctx = await browser.newContext({ viewport, deviceScaleFactor: 1, ...extra });
  await ctx.addInitScript((t) => localStorage.setItem("footscan.theme", t), theme);
  const page = await ctx.newPage();
  await page.goto(base);
  await page.locator("#statusPill[data-state=ok]").waitFor();
  return { ctx, page };
}

async function analyze(page, file) {
  await page.locator("#view-analyze input[type=file]").setInputFiles(fixture(file));
  await page.getByRole("button", { name: "Run analysis" }).click();
  await page.locator("#view-analyze .result-body").waitFor();
  await page.waitForTimeout(1800);
}

// Seed a patient with two visits so the timeline has content.
{
  const { ctx, page } = await open("dark", { width: 1360, height: 900 });
  await page.goto(`${base}/#/patients`);
  await page.getByLabel("New patient name or code").fill("Demo-0417");
  await page.getByRole("button", { name: "Add" }).click();
  for (const f of ["wound-baseline.jpg", "wound-followup.jpg"]) {
    await page.getByRole("button", { name: "New scan" }).click();
    await analyze(page, f);
    await page.getByRole("link", { name: "Patients" }).click();
    await page.getByRole("heading", { name: "Demo-0417" }).waitFor();
  }
  await ctx.close();
}

// 01: hero + analyze, 02: results
{
  const { ctx, page } = await open("dark", { width: 1360, height: 900 });
  await page.locator("#heroScene.is-3d").waitFor({ timeout: 20000 });
  await page.waitForTimeout(1200);
  await page.screenshot({ path: out("01-analyze.jpg"), ...shot });
  await analyze(page, "wound-baseline.jpg");
  await page.locator("#view-analyze .results").scrollIntoViewIfNeeded();
  await page.evaluate(() => window.scrollTo({ top: document.querySelector("#view-analyze .workspace").offsetTop - 90 }));
  await page.waitForTimeout(500);
  await page.screenshot({ path: out("02-analyze-results.jpg"), ...shot });
  await ctx.close();
}

// 03: compare
{
  const { ctx, page } = await open("dark", { width: 1360, height: 900 });
  await page.goto(`${base}/#/compare`);
  const inputs = page.locator("#view-compare input[type=file]");
  await inputs.nth(0).setInputFiles(fixture("wound-baseline.jpg"));
  await inputs.nth(1).setInputFiles(fixture("wound-followup.jpg"));
  await page.getByRole("button", { name: "Compare photos" }).click();
  await page.locator("#view-compare .result-body").waitFor();
  await page.waitForTimeout(1500);
  await page.evaluate(() => window.scrollTo({ top: 140 }));
  await page.waitForTimeout(400);
  await page.screenshot({ path: out("03-compare.jpg"), ...shot });
  await ctx.close();
}

// 04: patients timeline
{
  const { ctx, page } = await open("dark", { width: 1360, height: 900 });
  await page.goto(`${base}/#/patients`);
  await page.locator(".pitem").first().click();
  await page.locator(".timeline .tl__item").first().waitFor();
  await page.waitForTimeout(1800);
  await page.evaluate(() => window.scrollTo({ top: 120 }));
  await page.screenshot({ path: out("04-patients.jpg"), ...shot });
  await ctx.close();
}

// 05: light theme results, 06: mobile
{
  const { ctx, page } = await open("light", { width: 1360, height: 900 });
  await analyze(page, "wound-baseline.jpg");
  await page.evaluate(() => window.scrollTo({ top: document.querySelector("#view-analyze .workspace").offsetTop - 90 }));
  await page.waitForTimeout(500);
  await page.screenshot({ path: out("05-light-theme.jpg"), ...shot });
  await ctx.close();
}
{
  const { ctx, page } = await open("dark", { width: 390, height: 844 }, { deviceScaleFactor: 2, isMobile: true, hasTouch: true });
  await page.waitForTimeout(1500);
  await page.screenshot({ path: out("06-mobile.jpg"), ...shot });
  await ctx.close();
}

await browser.close();
console.log("screenshots written to docs/screenshots");
