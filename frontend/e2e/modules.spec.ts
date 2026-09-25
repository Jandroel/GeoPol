import { test, expect, type Page } from "@playwright/test";
import { execFileSync } from "node:child_process";
import { mkdir, readFile } from "node:fs/promises";
import { resolve } from "node:path";

test("five modules preserve upload context, separate flag10 exclusions and expose real statistics and guides", async ({
  page,
}) => {
  const username = process.env.GEOPOL_E2E_USER;
  const password = process.env.GEOPOL_E2E_PASSWORD;
  test.skip(
    !username || !password,
    "Use the isolated synthetic QA environment.",
  );
  const artifacts = resolve(process.env.GEOPOL_E2E_ARTIFACTS ?? "../.local");
  const fixtures = resolve(artifacts, "modules-fixtures");
  await mkdir(fixtures, { recursive: true });
  const python =
    process.env.GEOPOL_E2E_PYTHON ||
    resolve(
      "../backend/.venv",
      process.platform === "win32" ? "Scripts/python.exe" : "bin/python",
    );
  execFileSync(python, [resolve("e2e/fixtures/quality_excels.py"), fixtures]);
  execFileSync(python, [resolve("e2e/fixtures/modules_excel.py"), fixtures]);
  const errors: string[] = [];
  const externalRequests: string[] = [];
  const origin = new URL(process.env.GEOPOL_E2E_URL ?? "http://127.0.0.1:5174")
    .origin;
  page.on("pageerror", (error) => errors.push(error.message));
  page.on("request", (request) => {
    if (
      /^https?:/.test(request.url()) &&
      new URL(request.url()).origin !== origin
    )
      externalRequests.push(request.url());
  });
  async function capture(name: string, fullPage = true) {
    await page.evaluate(async () => {
      await document.fonts.ready;
      window.scrollTo(0, 0);
    });
    await page.screenshot({
      path: resolve(artifacts, `ui-modules-${name}.png`),
      fullPage,
      animations: "disabled",
    });
  }
  const navigation = page.getByRole("navigation", {
    name: "Navegación principal",
    exact: true,
  });
  const moduleNames = [
    "Vista general",
    "Validación",
    "Procedimientos",
    "Estadística",
    "Documentación",
  ];

  await page.goto("/");
  await page.getByLabel("Usuario", { exact: true }).fill(username!);
  await page.getByLabel("Contraseña", { exact: true }).fill(password!);
  await page
    .getByRole("button", { name: "Ingresar al espacio de trabajo" })
    .click();
  await expect(
    page.getByRole("heading", { name: "Vista general", exact: true }),
  ).toBeVisible();
  await expect(navigation.getByRole("link")).toHaveCount(5);
  for (const name of moduleNames)
    await expect(
      navigation.getByRole("link", { name, exact: true }),
    ).toBeVisible();
  await expect(page.locator("#source-file")).toBeVisible();
  await expect(page.locator(".reference-slot-toggle")).toHaveCount(5);

  const marker = Date.now();
  const referenceNames = [
    `QA módulos puertas ${marker}`,
    `QA módulos límites ${marker}`,
  ];
  await test.step("Save reference Excel files from the home workspace", async () => {
    for (const [index, kind, title] of [
      [0, "doors", "Puertas / viviendas"],
      [1, "boundaries", "Límites administrativos"],
    ] as const) {
      const card = page
        .locator("article.reference-slot")
        .filter({
          has: page.getByRole("button", {
            name: `Configurar referencia: ${title}`,
            exact: true,
          }),
        });
      const toggle = card.getByRole("button", {
        name: `Configurar referencia: ${title}`,
        exact: true,
      });
      await toggle.click();
      await card
        .getByLabel(`Archivo Excel · ${title}`, { exact: true })
        .setInputFiles(resolve(fixtures, `${kind}.xlsx`));
      await card
        .getByRole("button", {
          name: "Leer columnas de referencia",
          exact: true,
        })
        .click();
      await card
        .getByLabel("Nombre del catálogo", { exact: true })
        .fill(referenceNames[index]);
      await card
        .getByLabel("Versión de la fuente", { exact: true })
        .fill("modules-qa");
      await card
        .getByLabel("Origen de los datos / institución", { exact: true })
        .fill("SINTÉTICO: referencia artificial de QA aislada");
      await card
        .getByLabel(`Sistema de coordenadas · ${title}`)
        .selectOption("EPSG:4326");
      await card
        .getByLabel(`Documento que confirma WGS84 · ${title}`, { exact: true })
        .fill("Fixture artificial WGS84 EPSG:4326 para verificación aislada");
      await card
        .getByRole("button", {
          name: "Guardar y utilizar referencia",
          exact: true,
        })
        .click();
      await expect(
        card.getByRole("status", { name: "Disponibilidad de la referencia" }),
      ).toContainText("1 elementos disponibles");
      await toggle.click();
    }
    await expect(
      page.getByText("2 de 5 seleccionadas", { exact: true }),
    ).toBeVisible();
    await capture("home", false);
  });

  const runName = `QA cinco módulos ${marker}`;
  await test.step("Validate DATACRIM Excel and preserve the draft when returning home", async () => {
    await page
      .locator("#source-file")
      .setInputFiles(resolve(fixtures, "DATACRIM_25092026.xlsx"));
    const reportPromise = page.waitForResponse(
      (response) =>
        /\/api\/uploads\/[^/]+\/validation$/.test(
          new URL(response.url()).pathname,
        ) && response.request().method() === "POST",
    );
    await page
      .getByRole("button", { name: "Cargar y verificar columnas", exact: true })
      .click();
    await expect(page).toHaveURL(/\/validation$/);
    const reportResponse = await reportPromise;
    expect(reportResponse.status()).toBe(200);
    const report = await reportResponse.json();
    expect(report.ready).toBe(true);
    expect(report.filename.valid).toBe(true);
    expect(report.total_rows).toBe(6);
    expect(report.flag10_existing).toBe(1);
    expect(report.flag10_autoeligible).toBe(1);
    expect(report.columns.mapping.source_quality_flag).toBe("FLAG");
    const validation = page.getByRole("region", {
      name: "Comprobaciones del archivo",
    });
    await expect(validation).toHaveAttribute("aria-busy", "false");
    await expect(
      validation.getByText("FLAG 10 de origen", { exact: true }).locator(".."),
    ).toContainText("1");
    await expect(
      validation
        .getByText("Sin datos para ubicar", { exact: true })
        .locator(".."),
    ).toContainText("1");
    await expect(
      page.getByLabel("FLAG de origen", { exact: true }),
    ).toHaveValue("FLAG");
    await page
      .getByLabel("Nombre del procesamiento", { exact: true })
      .fill(runName);
    for (const name of referenceNames)
      await expect(page.locator(".validation-reference-summary")).toContainText(
        name,
      );
    await capture("validation");
    await navigation
      .getByRole("link", { name: "Vista general", exact: true })
      .click();
    await expect(
      page.getByRole("heading", { name: "Vista general", exact: true }),
    ).toBeVisible();
    await expect(
      page.getByText("DATACRIM_25092026.xlsx", { exact: true }),
    ).toBeVisible();
    await expect(
      page.getByText("2 de 5 seleccionadas", { exact: true }),
    ).toBeVisible();
    for (const name of referenceNames)
      await expect(
        page.locator(".reference-slot-toggle").filter({ hasText: name }),
      ).toBeVisible();
    await page
      .getByRole("link", { name: "Continuar validación", exact: true })
      .click();
    await expect(
      page.getByLabel("Nombre del procesamiento", { exact: true }),
    ).toHaveValue(runName);
    await expect(
      page.getByLabel("FLAG de origen", { exact: true }),
    ).toHaveValue("FLAG");
    await expect(
      page.getByRole("button", { name: "Iniciar procesamiento", exact: true }),
    ).toBeEnabled();
    await page
      .getByRole("button", { name: "Iniciar procesamiento", exact: true })
      .click();
    await expect(page).toHaveURL(/\/procedures\?run_id=/);
  });

  const runId = new URL(page.url()).searchParams.get("run_id")!;
  const token = await page.evaluate(() =>
    sessionStorage.getItem("geopol.session"),
  );
  const headers = { Authorization: `Bearer ${token}` };
  await expect(page.locator(".procedure-file .badge")).toHaveText(
    "Completado",
    { timeout: 120000 },
  );
  await test.step("Keep declared and inferred exclusions distinct from accepted and reviewable locations", async () => {
    const response = await page.request.get(
      `/api/runs/${runId}/results?page_size=100`,
      { headers },
    );
    expect(response.status()).toBe(200);
    const results = await response.json();
    expect(results.total).toBe(5);
    for (const complaint of ["QA-MOD-ORIGEN10", "QA-MOD-AUTO10"]) {
      const item = results.items.find(
        (row: { complaint_id: string }) => row.complaint_id === complaint,
      );
      expect(item.quality_flag).toBe(10);
      expect(item.review_state).toBe("excluded");
      expect(item.resolution).toBe("EXCLUIDO_FLAG_10");
      expect(item.latitude).toBeNull();
      expect(item.longitude).toBeNull();
    }
    expect(
      results.items.find(
        (row: { complaint_id: string }) => row.complaint_id === "QA-MOD-EXACTA",
      ).resolution,
    ).toBe("ACEPTADO_AUTOMATICO");
    expect(
      results.items.find(
        (row: { complaint_id: string }) =>
          row.complaint_id === "QA-MOD-SINMATCH",
      ).quality_flag,
    ).not.toBe(10);
    const qualityResponse = await page.request.get(
      `/api/runs/${runId}/quality`,
      { headers },
    );
    const quality = await qualityResponse.json();
    expect(quality.totals.excluded).toBe(2);
    expect(quality.totals.resolved).toBe(1);
    await expect(
      page.getByRole("complementary", {
        name: "Archivo y referencias del procesamiento",
      }),
    ).toContainText("DATACRIM_25092026.xlsx");
    for (const name of referenceNames)
      await expect(page.locator(".procedure-references")).toContainText(name);
    await expect(page.locator(".procedure-method")).toHaveCount(8);
    await page
      .locator(".procedure-method")
      .filter({ hasText: "Normalización" })
      .locator("summary")
      .click();
    await expect(page.locator(".procedure-method[open]")).toContainText(
      "Estandariza los campos",
    );
    await capture("procedures");
  });

  await test.step("Inspect complete statistics and download an Excel snapshot", async () => {
    await page
      .getByRole("link", { name: "Ver estadística", exact: true })
      .click();
    await expect(
      page.getByRole("heading", { name: "Estadística", exact: true }),
    ).toBeVisible();
    await expect(
      page.getByRole("heading", { name: "Mapa de resultados", exact: true }),
    ).toBeVisible();
    const response = await page.request.get(
      `/api/runs/${runId}/statistics?map_limit=500`,
      { headers },
    );
    expect(response.status()).toBe(200);
    const stats = await response.json();
    expect(stats.totals.units).toBe(5);
    expect(stats.totals.source_rows).toBe(6);
    expect(stats.totals.excluded).toBe(2);
    expect(stats.totals.mapped).toBe(1);
    expect(stats.map.total).toBe(1);
    await expect(page.locator(".statistics-map-canvas canvas")).toBeVisible();
    await assertRenderedReferencePoint(page);
    await expect(
      page.getByText("Excluidas · flag 10", { exact: true }).locator(".."),
    ).toContainText("2");
    await expect(
      page.getByRole("heading", {
        name: "Distribución territorial",
        exact: true,
      }),
    ).toBeVisible();
    await capture("statistics");
    await page
      .getByRole("checkbox", { name: /Referencia geográfica/ })
      .uncheck();
    await expect(
      page.getByText("Sin geometrías en esta vista", { exact: true }),
    ).toBeVisible();
    await expect(
      page.getByText("Con geometría aceptada", { exact: true }).locator(".."),
    ).toContainText("1");
    await page.getByRole("checkbox", { name: /Referencia geográfica/ }).check();
    await assertRenderedReferencePoint(page);
    await page
      .getByRole("tab", { name: "Detalle de registros", exact: true })
      .click();
    await page
      .getByLabel("Resolución", { exact: true })
      .selectOption("EXCLUIDO_FLAG_10");
    await expect(
      page.getByRole("status", { name: "Total de resultados" }),
    ).toContainText("Mostrando 1–2 de 2");
    await expect(
      page.getByRole("row").filter({ hasText: "QA-MOD-ORIGEN10" }),
    ).toBeVisible();
    await expect(
      page.getByRole("row").filter({ hasText: "QA-MOD-AUTO10" }),
    ).toBeVisible();
    await page.getByRole("tab", { name: "Descargas", exact: true }).click();
    await page.getByLabel("Perfil de exportación").selectOption("source_rows");
    await page
      .getByRole("button", { name: "Preparar exportación", exact: true })
      .click();
    const excelButton = page.getByRole("button", {
      name: "Descargar Excel",
      exact: true,
    });
    await expect(excelButton).toBeVisible({ timeout: 120000 });
    await expect(page.locator(".export-status")).toContainText("6 filas");
    const excelEvent = page.waitForEvent("download");
    await excelButton.click();
    const excel = await excelEvent;
    expect(excel.suggestedFilename()).toMatch(/\.xlsx$/);
    const bytes = await readFile((await excel.path())!);
    expect(bytes.subarray(0, 4).toString("hex")).toBe("504b0304");
  });

  await test.step("Search and download an actual documentation guide", async () => {
    await navigation
      .getByRole("link", { name: "Documentación", exact: true })
      .click();
    await expect(
      page.getByRole("heading", { name: "Documentación", exact: true }),
    ).toBeVisible();
    await page
      .getByRole("textbox", { name: "Buscar documentos", exact: true })
      .fill("Exportar resultados");
    await page
      .getByRole("button", { name: /^Exportar resultados a Excel/ })
      .click();
    const guide = page.getByRole("article", {
      name: "Exportar resultados a Excel",
      exact: true,
    });
    await expect(guide).toContainText("Preparar la descarga");
    const guideEvent = page.waitForEvent("download");
    await guide
      .getByRole("link", { name: "Descargar Markdown", exact: true })
      .click();
    const download = await guideEvent;
    expect(download.suggestedFilename()).toBe("geopol-exports.md");
    const body = await readFile((await download.path())!, "utf8");
    expect(body).toContain("# Exportar resultados a Excel");
    expect(body).toContain("Preparar exportación");
    await capture("documentation");
  });

  await test.step("Verify five-module navigation and statistics on a narrow screen", async () => {
    await navigation
      .getByRole("link", { name: "Estadística", exact: true })
      .click();
    await page
      .getByRole("combobox", { name: /^Procesamiento a consultar/ })
      .selectOption(runId);
    await expect(
      page.getByRole("heading", { name: "Mapa de resultados", exact: true }),
    ).toBeVisible();
    await page.setViewportSize({ width: 400, height: 900 });
    await assertRenderedReferencePoint(page);
    await capture("mobile-statistics");
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= window.innerWidth,
      ),
    ).toBe(true);
    await page
      .getByRole("button", { name: "Abrir navegación", exact: true })
      .click();
    const drawer = page.getByRole("dialog", {
      name: "Menú de navegación",
      exact: true,
    });
    await expect(drawer).toBeVisible();
    await expect(
      drawer
        .getByRole("navigation", { name: "Navegación principal" })
        .getByRole("link"),
    ).toHaveCount(5);
    await page.screenshot({
      path: resolve(artifacts, "ui-modules-mobile-menu.png"),
      animations: "disabled",
    });
    await page.keyboard.press("Escape");
    await expect(drawer).toHaveCount(0);
  });
  expect(errors).toEqual([]);
  expect(externalRequests).toEqual([]);
});

async function assertRenderedReferencePoint(page: Page) {
  await expect(
    page.getByRole("region", {
      name: "Mapa interactivo de geometrías aceptadas",
      exact: true,
    }),
  ).toHaveAttribute("aria-busy", "false");
  // Inspect the actual WebGL image: the blank background and controls cannot
  // satisfy the reference point's blue color, even when a canvas already exists.
  await expect
    .poll(
      async () => {
        const buffer = await page
          .locator(".statistics-map-canvas canvas")
          .screenshot();
        return page.evaluate(async (bytes) => {
          const bitmap = await createImageBitmap(
            new Blob([new Uint8Array(bytes)], { type: "image/png" }),
          );
          const canvas = document.createElement("canvas");
          canvas.width = bitmap.width;
          canvas.height = bitmap.height;
          const context = canvas.getContext("2d")!;
          context.drawImage(bitmap, 0, 0);
          const { data } = context.getImageData(
            0,
            0,
            canvas.width,
            canvas.height,
          );
          let pixels = 0;
          for (let i = 0; i < data.length; i += 4)
            if (
              data[i] < 35 &&
              data[i + 1] > 105 &&
              data[i + 1] < 145 &&
              data[i + 2] > 170 &&
              data[i + 2] < 215
            )
              pixels++;
          bitmap.close();
          return pixels;
        }, Array.from(buffer));
      },
      { timeout: 15000, intervals: [200, 500, 1000] },
    )
    .toBeGreaterThan(20);
}
