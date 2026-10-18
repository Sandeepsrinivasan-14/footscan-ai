import { fileURLToPath } from "node:url";
import path from "node:path";
import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";

const fixture = (name) => path.join(path.dirname(fileURLToPath(import.meta.url)), "..", "fixtures", name);

/** Collect console errors and CSP violations for the whole test. */
test.beforeEach(async ({ page }) => {
  page.problems = [];
  page.on("console", (msg) => {
    if (msg.type() === "error") page.problems.push(msg.text());
  });
  page.on("pageerror", (err) => page.problems.push(String(err)));
});
test.afterEach(async ({ page }) => {
  expect(page.problems, "no console errors or CSP violations").toEqual([]);
});

async function analyze(page, file) {
  await page.locator("#view-analyze input[type=file]").setInputFiles(fixture(file));
  await page.getByRole("button", { name: "Run analysis" }).click();
}

test("loads with the research-only disclaimer, model status and no CSP violations", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { level: 1 })).toContainText("See the wound");
  await expect(page.getByRole("note", { name: "Medical disclaimer" })).toContainText("Not a medical device");
  await expect(page.locator("#statusPill")).toHaveAttribute("data-state", "ok");
  await expect(page.getByRole("button", { name: "Run analysis" })).toBeDisabled();
  const csp = (await page.request.get("/")).headers()["content-security-policy"];
  expect(csp).toContain("default-src 'self'");
});

test("lazy-loads the three.js hero with SRI and enables it", async ({ page }) => {
  await page.goto("/");
  await expect(page.locator("#heroScene")).toHaveClass(/is-3d/, { timeout: 20_000 });
  expect(await page.evaluate(() => typeof window.THREE)).toBe("object");
  expect(await page.locator('script[src$="three.min.js"]').getAttribute("integrity")).toMatch(/^sha384-/);
});

test("respects prefers-reduced-motion by not animating the background", async ({ page }) => {
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.goto("/");
  const animation = await page.locator(".bg__blob--a").evaluate((el) => getComputedStyle(el).animationName);
  expect(animation).toBe("none");
});

test("theme toggle switches and persists", async ({ page }) => {
  await page.goto("/");
  const html = page.locator("html");
  const before = await html.getAttribute("data-theme");
  await page.getByRole("button", { name: /Switch to (light|dark) theme/ }).click();
  const after = await html.getAttribute("data-theme");
  expect(after).not.toBe(before);
  await page.reload();
  await expect(html).toHaveAttribute("data-theme", after);
});

test("analysis flow: upload, progress, results, opacity slider and layers", async ({ page }) => {
  await page.goto("/");
  await analyze(page, "wound-baseline.jpg");
  await expect(page.getByRole("progressbar", { name: "Analysis progress" })).toBeVisible();

  const results = page.locator("#view-analyze .result-body");
  await expect(results).toBeVisible();
  await expect(results).toContainText("Ulcer detected");
  await expect(results).toContainText("severity");
  await expect(results.locator(".metric")).toHaveCount(6);
  await expect(results).toContainText("Research use only");

  const slider = page.getByLabel("Overlay opacity");
  await slider.fill("25");
  await expect(page.locator(".viewer__opacity output")).toHaveText("25%");

  await page.getByRole("tab", { name: "Mask" }).click();
  await expect(page.getByRole("tab", { name: "Mask" })).toHaveAttribute("aria-selected", "true");
  await expect(slider).toBeDisabled();

  await page.getByRole("button", { name: "Side by side" }).click();
  await expect(page.locator(".viewer__frames")).toHaveClass(/is-split/);
});

test("rejects a non-image file with an error toast", async ({ page }) => {
  await page.goto("/");
  await page.locator("#view-analyze input[type=file]").setInputFiles(fixture("not-an-image.txt"));
  await expect(page.locator(".toast--error")).toContainText("Unsupported file");
  await expect(page.getByRole("button", { name: "Run analysis" })).toBeDisabled();
  page.problems.length = 0;
});

test("patients: create, save two scans, see the healing timeline", async ({ page }) => {
  await page.goto("/#/patients");
  await page.getByLabel("New patient name or code").fill("E2E-Patient");
  await page.getByRole("button", { name: "Add" }).click();
  await expect(page.getByRole("heading", { name: "E2E-Patient" })).toBeVisible();

  for (const file of ["wound-baseline.jpg", "wound-followup.jpg"]) {
    await page.getByRole("button", { name: "New scan" }).click();
    await expect(page.locator("#view-analyze")).toBeVisible();
    await expect(page.locator("#view-analyze select[name=patient_id] option:checked")).toHaveText("E2E-Patient");
    await analyze(page, file);
    await expect(page.locator("#view-analyze .result-body")).toBeVisible();
    await page.getByRole("link", { name: "Patients" }).click();
    await expect(page.getByRole("heading", { name: "E2E-Patient" })).toBeVisible();
  }

  await expect(page.getByText("2 saved scans")).toBeVisible();
  await expect(page.locator(".timeline .tl__item")).toHaveCount(2);
  await expect(page.locator(".chart__svg")).toBeVisible();
  await expect(page.locator(".delta--down")).toBeVisible(); // the follow-up wound is smaller

  const [download] = await Promise.all([
    page.waitForEvent("download"),
    page.getByRole("button", { name: /Download PDF report/ }).first().click(),
  ]);
  expect(download.suggestedFilename()).toMatch(/^footscan_report_.+\.pdf$/);
});

test("compare: baseline vs follow-up shows an improvement and a change map", async ({ page }) => {
  await page.goto("/#/compare");
  const inputs = page.locator("#view-compare input[type=file]");
  await inputs.nth(0).setInputFiles(fixture("wound-baseline.jpg"));
  await inputs.nth(1).setInputFiles(fixture("wound-followup.jpg"));
  await page.getByRole("button", { name: "Compare photos" }).click();
  const results = page.locator("#view-compare .result-body");
  await expect(results).toContainText("Improved");
  await expect(results.locator(".triptych img")).toHaveCount(3);
  await page.getByLabel("Swipe between baseline and follow-up").fill("80");
});

test("server errors surface as a toast and the form recovers", async ({ page }) => {
  await page.route("**/api/analyze", (route) =>
    route.fulfill({ status: 503, contentType: "application/json", body: JSON.stringify({ detail: "Segmentation model is unavailable" }) }),
  );
  await page.goto("/");
  await analyze(page, "wound-baseline.jpg");
  await expect(page.locator(".toast--error")).toContainText("Segmentation model is unavailable");
  await expect(page.getByRole("button", { name: "Run analysis" })).toBeEnabled();
  page.problems.length = 0; // the browser logs the mocked 503 as a console error
});

test("a 401 opens the API key dialog", async ({ page }) => {
  await page.route("**/api/patients?*", (route) =>
    route.fulfill({ status: 401, contentType: "application/json", body: JSON.stringify({ detail: "Invalid or missing API key" }) }),
  );
  await page.goto("/");
  await expect(page.getByRole("dialog", { name: "API key" })).toBeVisible();
  page.problems.length = 0;
});

for (const theme of ["dark", "light"]) {
  test(`has no detectable accessibility violations (${theme})`, async ({ page }) => {
    await page.addInitScript((t) => localStorage.setItem("footscan.theme", t), theme);
    await page.goto("/");
    await analyze(page, "wound-baseline.jpg");
    await expect(page.locator("#view-analyze .result-body")).toBeVisible();
    await page.waitForTimeout(1500); // let entry animations settle so contrast is measured on final colours
    const results = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"]).analyze();
    expect(results.violations.map((v) => `${v.id}: ${v.nodes.map((n) => n.target.join(" ")).join(" | ")}`)).toEqual([]);
  });
}

test("@mobile fits the viewport without horizontal scroll and keeps the bottom nav reachable", async ({ page }) => {
  await page.goto("/");
  await analyze(page, "wound-baseline.jpg");
  await expect(page.locator("#view-analyze .result-body")).toBeVisible();
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
  expect(overflow).toBeLessThanOrEqual(1);
  const nav = await page.locator(".nav").boundingBox();
  const vh = page.viewportSize().height;
  expect(nav.y + nav.height).toBeGreaterThan(vh - 40); // docked at the bottom
  await page.getByRole("link", { name: "Compare" }).click();
  await expect(page.getByRole("heading", { level: 1 })).toContainText("Compare");
});
