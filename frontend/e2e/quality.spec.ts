import { test, expect } from "@playwright/test";
import { execFileSync } from "node:child_process";
import { mkdir, readFile } from "node:fs/promises";
import { resolve } from "node:path";

test("five reference Excels, staged qualities and independent export preserve completed doors", async ({
  page,
}) => {
  const username = process.env.GEOPOL_E2E_USER;
  const password = process.env.GEOPOL_E2E_PASSWORD;
  test.skip(
    !username || !password,
    "Use the isolated synthetic QA environment.",
  );
  const artifacts = resolve(process.env.GEOPOL_E2E_ARTIFACTS ?? "../.local");
  const fixtures = resolve(artifacts, "quality-fixtures");
  await mkdir(fixtures, { recursive: true });
  const python = resolve(
    "../backend/.venv",
    process.platform === "win32" ? "Scripts/python.exe" : "bin/python",
  );
  execFileSync(python, [resolve("e2e/fixtures/quality_excels.py"), fixtures]);
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.goto("/");
  await page.getByLabel("Usuario", { exact: true }).fill(username!);
  await page.getByLabel("Contraseña", { exact: true }).fill(password!);
  await page
    .getByRole("button", { name: "Ingresar al espacio de trabajo" })
    .click();
  await expect(
    page.getByRole("heading", { name: "Resumen", exact: true }),
  ).toBeVisible();
  await page.goto("/runs/new");
  await page.evaluate(async () => {
    await document.fonts.ready;
    window.scrollTo(0, 0);
  });
  await expect(
    page.getByRole("region", { name: "Cinco archivos de referencia" }),
  ).toBeVisible();
  await page.screenshot({
    path: resolve(artifacts, "ui-quality-upload.png"),
    fullPage: true,
  });
  for (const [kind, title] of [
    ["doors", "Puertas / viviendas"],
    ["roads", "Vías y cuadras"],
    ["centers", "Centros poblados"],
    ["boundaries", "Límites administrativos"],
    ["jurisdictions", "Jurisdicciones"],
  ]) {
    const card = page
      .locator("article.reference-slot")
      .filter({ has: page.getByRole("heading", { name: title, exact: true }) });
    await card.locator("summary").first().click();
    await card
      .getByLabel(`Archivo Excel · ${title}`, { exact: true })
      .setInputFiles(resolve(fixtures, `${kind}.xlsx`));
    await card
      .getByRole("button", { name: "Leer columnas de referencia", exact: true })
      .click();
    await card
      .getByLabel("Versión de la fuente", { exact: true })
      .fill("qa-quality-1");
    await card
      .getByLabel("Fuente / institución", { exact: true })
      .fill("SINTÉTICO: prueba aislada, sin uso operativo");
    await card
      .getByLabel(`Sistema de coordenadas · ${title}`)
      .selectOption("EPSG:4326");
    await card
      .getByLabel(`Documento que confirma WGS84 · ${title}`, { exact: true })
      .fill("Coordenadas artificiales EPSG:4326 de la fixture QA");
    await card
      .getByRole("button", {
        name: "Guardar y utilizar referencia",
        exact: true,
      })
      .click();
    await expect(card.getByRole("status")).toContainText(
      "1 elementos disponibles",
    );
    await card.locator("summary").first().click();
  }
  await page
    .locator("#source-file")
    .setInputFiles(resolve(fixtures, "pnp.xlsx"));
  await page
    .getByRole("button", { name: "Cargar y verificar columnas", exact: true })
    .click();
  const runName = `QA calidad Excel ${Date.now()}`;
  await page
    .getByLabel("Nombre del procesamiento", { exact: true })
    .fill(runName);
  await expect(page.getByLabel("Flujo de procesamiento")).toHaveValue(
    "quality_v1",
  );
  await page
    .getByRole("button", { name: "Iniciar procesamiento", exact: true })
    .click();
  await expect(page.locator(".page-heading .badge")).toHaveText("Completado", {
    timeout: 120000,
  });
  const runId = new URL(page.url()).pathname.split("/").at(-1)!;
  const token = await page.evaluate(() =>
    sessionStorage.getItem("geopol.session"),
  );
  const headers = { Authorization: `Bearer ${token}` };
  const before = await (
    await page.request.get(`/api/runs/${runId}/results`, { headers })
  ).json();
  const exact = before.items.find(
    (r: { complaint_id: string }) => r.complaint_id === "QA-PUERTA",
  );
  expect(exact).toBeTruthy();
  expect(exact.quality_flag).toBe(1);
  expect(exact.review_state).toBe("automatic");
  expect(
    before.items.some(
      (r: { quality_flag: number; review_state: string }) =>
        r.quality_flag === 1 && r.review_state === "quick_review",
    ),
  ).toBe(true);
  expect(
    before.items.find(
      (r: { complaint_id: string }) => r.complaint_id === "QA-INCOMPLETA",
    ).quality_flag,
  ).toBeNull();
  expect(
    before.items.find(
      (r: { complaint_id: string }) => r.complaint_id === "QA-NUCLEO",
    ).quality_flag,
  ).toBe(2);
  await page
    .getByRole("tab", { name: "Seguimiento por calidad", exact: true })
    .click();
  await expect(
    page.getByRole("heading", { name: "Avance por calidad", exact: true }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Continuar con cuadras" }).click();
  await expect(page.locator(".page-heading .badge")).toHaveText("Completado", {
    timeout: 120000,
  });
  await expect
    .poll(async () => {
      const response = await page.request.get(`/api/runs/${runId}/results`, {
        headers,
      });
      const results = await response.json();
      return results.items.some(
        (r: {
          quality_flag: number;
          quality_stage: string;
          review_state: string;
        }) =>
          r.quality_flag === 1 &&
          r.quality_stage === "block" &&
          r.review_state === "automatic",
      );
    })
    .toBe(true);
  const after = await (
    await page.request.get(`/api/results/${exact.id}`, { headers })
  ).json();
  expect(after.revision).toBe(exact.revision);
  expect(after.latitude).toBe(exact.latitude);
  expect(after.longitude).toBe(exact.longitude);
  expect(after.quality_flag).toBe(1);
  expect(after.review_state).toBe("automatic");
  await expect(page.locator(".page-heading .badge")).toHaveText("Completado", {
    timeout: 20000,
  });
  await expect(page.locator(".quality-progress-summary")).toContainText(
    "2 de 5 ubicaciones resueltas",
    { timeout: 20000 },
  );
  const blockRow = page.getByRole("row").filter({ hasText: "QA-CUADRA" });
  await expect(blockRow).toContainText("Aceptado automáticamente", {
    timeout: 20000,
  });
  await expect(blockRow.locator(".quality-cell")).toContainText("Cuadras");
  await expect(blockRow).not.toContainText("Sin coincidencia");
  await page.screenshot({
    path: resolve(artifacts, "ui-quality-stages.png"),
    fullPage: true,
  });
  await page.setViewportSize({ width: 400, height: 900 });
  await page.screenshot({
    path: resolve(artifacts, "ui-quality-mobile.png"),
    fullPage: true,
  });
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBe(true);
  await page.setViewportSize({ width: 1440, height: 1000 });
  await page.getByLabel("Flag de calidad del filtro").selectOption("1");
  await page
    .getByLabel("Estado de revisión del filtro")
    .selectOption("quick_review");
  await expect(
    page.getByRole("link", { name: "Abrir revisión rápida", exact: true }),
  ).toHaveAttribute("href", /quality_flag=1.*review_state=quick_review/);
  const quick = await (
    await page.request.get(
      `/api/runs/${runId}/results?quality_flag=1&review_state=quick_review`,
      { headers },
    )
  ).json();
  expect(quick.total).toBe(1);
  expect(quick.items[0].complaint_id).toBe("QA-ERRATA");
  await page.getByLabel("Estado de revisión del filtro").selectOption("");
  await page
    .getByRole("button", { name: "Preparar exportación", exact: true })
    .first()
    .click();
  const downloadButton = page
    .getByRole("button", { name: "Descargar Excel", exact: true })
    .first();
  await expect(downloadButton).toBeVisible({ timeout: 120000 });
  const event = page.waitForEvent("download");
  await downloadButton.click();
  const downloaded = await event;
  expect(downloaded.suggestedFilename()).toMatch(/\.xlsx$/);
  const bytes = await readFile((await downloaded.path())!);
  expect(bytes.subarray(0, 4).toString("hex")).toBe("504b0304");
  expect(errors).toEqual([]);
});
