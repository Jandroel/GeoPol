import { test, expect } from "@playwright/test";
import { mkdir } from "node:fs/promises";
import { resolve } from "node:path";

test("live operation, interactive charts and collapsible navigation remain distinct", async ({
  page,
}) => {
  const username = process.env.GEOPOL_E2E_USER;
  const password = process.env.GEOPOL_E2E_PASSWORD;
  test.skip(
    !username || !password,
    "Use the isolated synthetic QA environment.",
  );
  const artifacts = resolve(process.env.GEOPOL_E2E_ARTIFACTS ?? "../.local");
  await mkdir(artifacts, { recursive: true });
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await page.goto("/");
  await page.getByLabel("Usuario", { exact: true }).fill(username!);
  await page.getByLabel("Contraseña", { exact: true }).fill(password!);
  await page
    .getByRole("button", { name: "Ingresar al espacio de trabajo" })
    .click();
  await expect(
    page.getByRole("heading", { name: "Vista general", exact: true }),
  ).toBeVisible();

  // Stable artificial response allows visual/timer QA without holding or changing a real job.
  const id = "synthetic-visual-activity";
  const start = new Date(Date.now() - 125000).toISOString();
  const stages = [
    ["door", "Puertas"],
    ["block", "Cuadras"],
    ["intersection", "Cruces de vías"],
    ["street", "Vías"],
    ["nucleus", "Núcleos y centros poblados"],
    ["jurisdiction", "Jurisdicciones"],
  ].map(([key, label], index) => ({
    key,
    label,
    units: index ? 0 : 100,
    source_rows: index ? 0 : 120,
    resolved: index ? 0 : 40,
    review: index ? 0 : 20,
    unmatched: index ? 0 : 30,
    blocked: index ? 0 : 10,
    percent_of_total: index ? 0 : 100,
  }));
  const run = {
    id,
    name: "Demostración visual · datos sintéticos",
    filename: "muestra_sintetica.xlsx",
    status: "PROCESSING",
    created_at: start,
    started_at: start,
    source_rows: 120,
    location_units: 100,
    processed_units: 100,
    issue_rows: 0,
    counts: {},
    config: { workflow: "quality_v1", quality_target_stage: "block" },
    activity: {
      job_id: "synthetic-job",
      status: "RUNNING",
      phase: "resolution",
      stage: "block",
      queued_at: start,
      started_at: start,
      finished_at: null,
      processed_units: 12,
      total_units: 40,
      source_rows: 120,
      worker_online: true,
    },
  };
  const overview = {
    run_id: id,
    workflow: "quality_v1",
    policy_version: "quality-2.0",
    provisional: true,
    totals: {
      units: 100,
      source_rows: 120,
      resolved: 40,
      review: 20,
      unmatched: 30,
      blocked: 10,
      unprocessed: 0,
    },
    qualities: [],
    flags: [
      { flag: 1, units: 70, source_rows: 90 },
      { flag: 2, units: 30, source_rows: 30 },
    ],
    review_states: [{ state: "automatic", units: 40, source_rows: 50 }],
    stages,
    next_stage: null,
    eligible_units: 0,
    held_review_units: 20,
    can_advance: false,
  };
  await page.route(`**/api/runs/${id}**`, async (route) => {
    const path = new URL(route.request().url()).pathname;
    await route.fulfill({
      json: path.endsWith("/quality")
        ? overview
        : path.endsWith("/results")
          ? { items: [], total: 0, page: 1, page_size: 25 }
          : run,
    });
  });
  await page.goto(`/runs/${id}?tab=quality`);
  const activity = page.getByRole("region", {
    name: "Actividad del procesamiento",
  });
  await expect(
    activity.getByRole("heading", { name: "Procesamiento en curso" }),
  ).toBeVisible();
  await expect(activity).toContainText("muestra_sintetica.xlsx");
  await expect(activity.getByRole("progressbar")).toHaveAttribute(
    "aria-valuenow",
    "30",
  );
  await expect(activity).toContainText("12 de 40");
  const timer = activity.getByRole("timer");
  const initialTime = await timer.textContent();
  await expect(timer).not.toHaveText(initialTime!);
  await expect(activity.locator(".run-activity__spinner")).toHaveCSS(
    "animation-name",
    "none",
  );
  await page.screenshot({
    path: resolve(artifacts, "ui-processing-active.png"),
  });

  const firstChart = page.locator(".quality-stage-card").first();
  const segment = firstChart.getByRole("button", { name: /^Por revisar/ });
  await segment.click();
  await expect(segment).toHaveAttribute("aria-pressed", "true");
  const tooltip = firstChart.locator(".stage-pie-tooltip");
  await expect(tooltip).toContainText("Por revisar");
  await expect(tooltip).toContainText("20");
  await expect(tooltip).toContainText("20 %");
  await expect(firstChart.locator(".stage-pie-total")).toContainText("100");
  await expect(firstChart.locator(".stage-visual-detail")).toContainText(
    "20 de 100",
  );
  await expect(page.getByLabel("Flag de calidad del filtro")).toHaveValue("");
  await expect(page.getByLabel("Estado de revisión del filtro")).toHaveValue(
    "",
  );
  await expect(page.getByLabel("Etapa del filtro")).toHaveValue("");
  await page.screenshot({
    path: resolve(artifacts, "ui-processing-charts.png"),
  });
  await segment.press("Escape");
  await expect(segment).toHaveAttribute("aria-pressed", "false");
  await expect(tooltip).toHaveCount(0);
  const resolvedSlice = firstChart.locator(
    '.stage-pie-slice[data-slice="resolved"] .stage-pie-hit',
  );
  await resolvedSlice.hover();
  await expect(tooltip).toContainText("Resueltos");
  await expect(tooltip).toContainText("40 %");

  for (const width of [1280, 1024, 768]) {
    await page.setViewportSize({ width, height: 900 });
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= window.innerWidth,
      ),
    ).toBe(true);
    await expect(
      firstChart.getByRole("button", { name: /^Referencia/ }),
    ).toBeVisible();
  }

  await page
    .getByRole("button", { name: "Contraer menú", exact: true })
    .click();
  await expect(
    page.getByRole("button", { name: "Expandir menú", exact: true }),
  ).toHaveAttribute("aria-expanded", "false");
  expect((await page.locator(".sidebar").boundingBox())!.width).toBeLessThan(
    110,
  );
  await page
    .getByRole("button", { name: "Expandir menú", exact: true })
    .click();
  await page.setViewportSize({ width: 375, height: 820 });
  await page.evaluate(() => window.scrollTo(0, 0));
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBe(true);
  const open = page.getByRole("button", {
    name: "Abrir navegación",
    exact: true,
  });
  await open.click();
  const drawer = page.getByRole("dialog", { name: "Menú de navegación" });
  await expect(drawer).toBeVisible();
  await expect(
    drawer.getByRole("button", { name: "Cerrar navegación" }),
  ).toBeFocused();
  await page.screenshot({
    path: resolve(artifacts, "ui-navigation-mobile.png"),
  });
  await page.keyboard.press("Escape");
  await expect(drawer).toHaveCount(0);
  await expect(open).toBeFocused();
  await expect(page.locator("body")).not.toHaveCSS("overflow", "hidden");
  await page.goto(`/quality?run_id=${id}`);
  await expect(activity).toHaveCount(1);
  await expect(activity).toContainText("muestra_sintetica.xlsx");
  await expect(activity.getByRole("progressbar")).toHaveAttribute(
    "aria-valuenow",
    "30",
  );
  const mobileCategory = firstChart.getByRole("button", {
    name: /^Sin coincidencia/,
  });
  await mobileCategory.click();
  await expect(mobileCategory).toHaveAttribute("aria-pressed", "true");
  await expect(firstChart.locator(".stage-pie-tooltip")).toContainText("30 %");
  await expect(page.getByLabel("Flag de calidad del filtro")).toHaveValue("");
  await expect(page.getByLabel("Estado de revisión del filtro")).toHaveValue(
    "",
  );
  await expect(page.getByLabel("Etapa del filtro")).toHaveValue("");
  await firstChart.screenshot({
    path: resolve(artifacts, "ui-pie-mobile.png"),
  });
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBe(true);
  expect(errors).toEqual([]);
});
