import { test, expect, type Page } from "@playwright/test";
import { execFileSync } from "node:child_process";
import { mkdir, readFile } from "node:fs/promises";
import { resolve } from "node:path";

test("five modules preserve data, render both themes and expose statistics and readable guides", async ({
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
  async function setTheme(theme: "light" | "dark") {
    const changed =
      (await page.locator("html").getAttribute("data-theme")) !== theme;
    if (changed)
      await page
        .getByRole("button", {
          name: theme === "dark" ? "Activar tema oscuro" : "Activar tema claro",
          exact: true,
        })
        .click();
    await expect(page.locator("html")).toHaveAttribute("data-theme", theme);
    if (changed)
      await expect
        .poll(() => page.evaluate(() => localStorage.getItem("geopol.theme")))
        .toBe(theme);
  }
  async function assertOverviewBackground(theme: "light" | "dark") {
    const workspace = page.locator(".workspace-overview");
    const expectedPath = `/images/overview-peru-${theme}.png`;
    await expect(workspace).toHaveCount(1);
    await expect(workspace).toHaveCSS(
      "background-image",
      new RegExp(`overview-peru-${theme}\\.png`),
    );
    const image = await workspace.evaluate(async (element, path) => {
      const background = getComputedStyle(element).backgroundImage;
      const urls = [...background.matchAll(/url\(["']?([^"')]+)["']?\)/g)];
      const source = urls.find(
        ([, url]) => new URL(url, location.href).pathname === path,
      )?.[1];
      if (!source) return null;
      const image = new Image();
      image.src = source;
      await image.decode();
      return {
        origin: new URL(image.src).origin,
        width: image.naturalWidth,
        height: image.naturalHeight,
      };
    }, expectedPath);
    expect(image?.origin).toBe(origin);
    expect(image?.width).toBeGreaterThan(0);
    expect(image?.height).toBeGreaterThan(0);
  }
  async function assertHomeDesktopLayout() {
    await page.evaluate(() => window.scrollTo(0, 0));
    const workspace = await page.locator(".workspace-overview").boundingBox();
    const source = await page
      .locator(".overview-imports .intake-source")
      .boundingBox();
    const references = await page
      .locator(".overview-imports .reference-upload-column")
      .boundingBox();
    expect(workspace).not.toBeNull();
    expect(source).not.toBeNull();
    expect(references).not.toBeNull();
    // The supplied backgrounds place Peru on the right. Preserve that region
    // at each desktop size instead of allowing the upload cards to cover it.
    const mapRegion = workspace!.x + workspace!.width * 0.6;
    for (const panel of [source!, references!]) {
      expect(panel.x).toBeGreaterThanOrEqual(workspace!.x);
      expect(panel.x + panel.width).toBeLessThanOrEqual(mapRegion);
      expect(panel.width).toBeGreaterThan(280);
      expect(panel.y + panel.height).toBeLessThanOrEqual(
        page.viewportSize()!.height + 1,
      );
    }
    expect(source!.y + source!.height).toBeLessThanOrEqual(references!.y + 1);
    expect(Math.abs(source!.x - references!.x)).toBeLessThanOrEqual(1);
    await expect(page.locator(".reference-direct-row").last()).toBeInViewport({
      ratio: 1,
    });
    await expect
      .poll(
        () =>
          page.evaluate(() => {
            const scrollHeight = document.documentElement.scrollHeight;
            const scrollWidth = document.documentElement.scrollWidth;
            if (
              scrollHeight <= window.innerHeight + 1 &&
              scrollWidth <= window.innerWidth
            )
              return "fits";
            const source = document.querySelector(
              ".overview-imports .intake-source",
            );
            const references = document.querySelector(
              ".overview-imports .reference-upload-column",
            );
            const content = document.querySelector(".main-content");
            return JSON.stringify({
              scrollHeight,
              scrollWidth,
              viewportWidth: window.innerWidth,
              viewportHeight: window.innerHeight,
              sourceBottom: source?.getBoundingClientRect().bottom,
              referencesBottom: references?.getBoundingClientRect().bottom,
              contentPaddingBottom: content
                ? getComputedStyle(content).paddingBottom
                : null,
            });
          }),
        { message: "Vista general debe caber en el escritorio sin scroll" },
      )
      .toBe("fits");
  }
  async function captureThemes(name: string, map = false) {
    const home = name === "home" || name === "home-loaded";
    await expect(page.locator("img.overview-artwork")).toHaveCount(0);
    for (const theme of ["light", "dark"] as const) {
      await page.setViewportSize(
        name === "home-loaded"
          ? { width: 1366, height: 768 }
          : { width: 1440, height: 1000 },
      );
      await setTheme(theme);
      if (home) {
        await assertOverviewBackground(theme);
      } else {
        await expect(page.locator(".workspace-overview")).toHaveCount(0);
        for (const workspace of await page.locator(".workspace").all())
          await expect(workspace).not.toHaveCSS(
            "background-image",
            /overview-peru-(?:light|dark)\.png/,
          );
      }
      if (map) await assertRenderedReferencePoint(page);
      await capture(`${name}-${theme}`);
      if (home) await assertHomeDesktopLayout();
      await page.setViewportSize({ width: 400, height: 900 });
      if (home) await assertOverviewBackground(theme);
      if (map) await assertRenderedReferencePoint(page);
      await capture(`mobile-${name}-${theme}`);
      if (name === "home-loaded") {
        const source = page.locator(".overview-imports .intake-source");
        const continuation = source.getByRole("link", {
          name: "Continuar validación",
          exact: true,
        });
        await expect(source).toBeVisible();
        await expect(continuation).toBeVisible();
        const sourceBox = await source.boundingBox();
        const continuationBox = await continuation.boundingBox();
        expect(sourceBox).not.toBeNull();
        expect(continuationBox).not.toBeNull();
        for (const box of [sourceBox!, continuationBox!]) {
          expect(box.x).toBeGreaterThanOrEqual(0);
          expect(box.x + box.width).toBeLessThanOrEqual(
            page.viewportSize()!.width + 1,
          );
        }
        expect(continuationBox!.x).toBeGreaterThanOrEqual(sourceBox!.x);
        expect(continuationBox!.x + continuationBox!.width).toBeLessThanOrEqual(
          sourceBox!.x + sourceBox!.width + 1,
        );
      }
      expect(
        await page.evaluate(
          () => document.documentElement.scrollWidth <= window.innerWidth,
        ),
      ).toBe(true);
    }
    await page.setViewportSize({ width: 1440, height: 1000 });
    await setTheme("light");
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

  await page.emulateMedia({ colorScheme: "light" });
  await page.goto("/");
  await expect(
    page.getByRole("heading", { name: "Bienvenido a GeoPol", exact: true }),
  ).toBeVisible();
  await test.step("Switch login theme and preserve the explicit choice after reload", async () => {
    await expect(page.locator("html")).toHaveAttribute("data-theme", "light");
    await page.emulateMedia({ colorScheme: "dark" });
    await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
    await page.emulateMedia({ colorScheme: "light" });
    await expect(page.locator("html")).toHaveAttribute("data-theme", "light");
    await captureThemes("login");
    await setTheme("dark");
    await page.reload();
    await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
    await expect(
      page.getByRole("button", { name: "Activar tema claro", exact: true }),
    ).toBeVisible();
  });
  await page.getByLabel("Usuario", { exact: true }).fill(username!);
  await page.getByLabel("Contraseña", { exact: true }).fill(password!);
  await page
    .getByRole("button", { name: "Ingresar al espacio de trabajo" })
    .click();
  await expect(
    page.getByRole("heading", { name: "Vista general", exact: true }),
  ).toBeVisible();
  await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
  await expect(
    page.getByRole("navigation", { name: "Ubicación actual", exact: true }),
  ).toHaveCount(0);
  await expect(page.locator('a[href="/demo.csv"]')).toHaveCount(0);
  await expect(
    page.getByRole("heading", {
      name: "Procesamientos recientes",
      exact: true,
    }),
  ).toHaveCount(0);
  await expect(
    page.getByText("Estado de la información", { exact: true }),
  ).toHaveCount(0);
  await expect(page.locator(".overview-introduction")).toHaveCSS(
    "border-top-width",
    "0px",
  );
  await expect(page.locator(".overview-introduction")).toHaveCSS(
    "background-color",
    "rgba(0, 0, 0, 0)",
  );
  async function assertHomeFits(state: string) {
    for (const [width, height] of [
      [1366, 768],
      [1440, 900],
      [1920, 1080],
    ]) {
      await page.setViewportSize({ width, height });
      await assertOverviewBackground(
        (await page.locator("html").getAttribute("data-theme")) as
          "light" | "dark",
      );
      await capture(`home-${state}-${width}x${height}`);
      await assertHomeDesktopLayout();
    }
    await page.setViewportSize({ width: 1440, height: 1000 });
  }
  await assertHomeFits("empty");
  for (const width of [800, 1024]) {
    await page.setViewportSize({ width, height: 900 });
    await capture(`home-intermediate-${width}`);
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth,
      ),
    ).toBe(true);
  }
  await page.setViewportSize({ width: 1440, height: 1000 });
  await expect(navigation.getByRole("link")).toHaveCount(5);
  for (const name of moduleNames)
    await expect(
      navigation.getByRole("link", { name, exact: true }),
    ).toBeVisible();
  await expect(page.locator("#source-file")).toBeVisible();
  await expect(page.locator(".reference-direct-row")).toHaveCount(5);
  await expect(
    page.getByRole("link", { name: "Auditoría", exact: true }),
  ).toHaveCount(0);

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
      const card = page.locator("article.reference-slot").filter({
        has: page.getByRole("heading", {
          name: title,
          exact: true,
          includeHidden: true,
        }),
      });
      const attach = card.getByRole("button", {
        name: `Adjuntar Excel · ${title}`,
        exact: true,
      });
      const dialog = page.getByRole("dialog", {
        name: `Configurar ${title}`,
        exact: true,
      });
      const chooserPromise = page.waitForEvent("filechooser");
      await attach.click();
      const chooser = await chooserPromise;
      await expect(dialog).not.toBeVisible();
      await chooser.setFiles(resolve(fixtures, `${kind}.xlsx`));
      await expect(dialog).toBeVisible();
      if (index === 0) {
        await page.keyboard.press("Escape");
        await expect(dialog).not.toBeVisible();
        await expect(
          card.getByRole("button", {
            name: `Cambiar Excel · ${title}`,
            exact: true,
          }),
        ).toBeFocused();
        await card
          .getByRole("button", {
            name: `Configurar referencia: ${title}`,
            exact: true,
          })
          .click();
      }
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
      if (index === 0) {
        for (const theme of ["light", "dark"] as const) {
          // Native dialogs make background controls inert; set the existing
          // theme through the DOM only for this visual fixture.
          await page.locator("html").evaluate((html, value) => {
            html.setAttribute("data-theme", value);
          }, theme);
          for (const [width, height] of [
            [1366, 768],
            [400, 900],
          ]) {
            await page.setViewportSize({ width, height });
            await dialog
              .locator(".reference-dialog-content")
              .evaluate((node) => {
                node.scrollTop = 0;
              });
            await capture(`reference-dialog-${theme}-${width}`, false);
            expect(
              await page.evaluate(
                () => document.documentElement.scrollWidth <= innerWidth,
              ),
            ).toBe(true);
            const box = await dialog.boundingBox();
            expect(box!.height).toBeLessThan(height);
            expect(box!.width).toBeLessThan(width);
          }
        }
        await page.setViewportSize({ width: 1440, height: 1000 });
      }
      await card
        .getByRole("button", {
          name: "Guardar y utilizar referencia",
          exact: true,
        })
        .click();
      await expect(
        card.getByRole("status", { name: "Disponibilidad de la referencia" }),
      ).toContainText("1 elementos disponibles");
      await dialog
        .getByRole("button", {
          name: `Cerrar configuración de ${title}`,
          exact: true,
        })
        .click();
      await expect(dialog).not.toBeVisible();
      await expect(attach).toBeFocused();
    }
    await expect(
      page.getByText("2 de 5 seleccionadas", { exact: true }),
    ).toBeVisible();
    await assertHomeFits("references");
    await captureThemes("home");
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
      .getByRole("button", { name: "Continuar validación", exact: true })
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
    await captureThemes("validation");
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
        page.locator(".reference-direct-row").filter({ hasText: name }),
      ).toBeVisible();
    await assertHomeFits("loaded");
    await captureThemes("home-loaded");
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
  await test.step("Open the latest processing by default in both modules", async () => {
    await page.goto("/procedures");
    await expect(page).toHaveURL(new RegExp(`/procedures\\?run_id=${runId}`));
    await expect(page.getByLabel("Procesamiento a consultar")).toHaveValue(
      runId,
    );
    await page.goto("/statistics");
    await expect(page).toHaveURL(new RegExp(`/statistics\\?run_id=${runId}`));
    await page.goto(`/procedures?run_id=${runId}`);
  });
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
    await captureThemes("procedures");
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
    await captureThemes("statistics", true);
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
    await page
      .getByRole("row")
      .filter({ hasText: "QA-MOD-ORIGEN10" })
      .getByRole("link", { name: "Examinar", exact: true })
      .click();
    await expect(page).toHaveURL(/\/results\//);
    await expect(
      page.getByText(/Esta fila se conserva con FLAG 10/),
    ).toBeVisible();
    await expect(
      page.getByRole("button", { name: "Tomar revisión", exact: true }),
    ).toHaveCount(0);
    await captureThemes("result-flag10");
    await page.locator(".back-link").click();
    await expect(
      page.getByRole("tab", { name: "Detalle de registros", exact: true }),
    ).toHaveAttribute("aria-selected", "true");
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

  await test.step("Read the guide without Markdown downloads, source footers or audit navigation", async () => {
    await navigation
      .getByRole("link", { name: "Documentación", exact: true })
      .click();
    await expect(
      page.getByRole("heading", { name: "Documentación", exact: true }),
    ).toBeVisible();
    await expect(
      page.getByRole("link", { name: "Auditoría", exact: true }),
    ).toHaveCount(0);
    await page.goto("/audit");
    await expect(page).toHaveURL(/\/documentation$/);
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
    await expect(guide).toContainText("Preparar exportación");
    await expect(page.getByText(/Markdown/)).toHaveCount(0);
    await expect(guide.locator("a[download], footer")).toHaveCount(0);
    await expect(
      page.getByText(/Adaptado de|no es un PDF oficial|Fuentes internas/),
    ).toHaveCount(0);
    await expect(guide.getByText(/docs\//)).toHaveCount(0);
    await captureThemes("documentation");

    await page
      .getByRole("button", { name: "Limpiar búsqueda", exact: true })
      .click();
    await expect(
      page.getByRole("textbox", { name: "Buscar documentos", exact: true }),
    ).toHaveValue("");
    const categories = page.getByRole("navigation", {
      name: "Categorías de documentación",
      exact: true,
    });
    const proceduresCategory = categories.getByRole("button", {
      name: "Procedimientos",
      exact: true,
    });
    await proceduresCategory.click();
    await expect(proceduresCategory).toHaveAttribute("aria-pressed", "true");
    const catalog = page.locator(".documentation-catalog");
    await expect(catalog.locator(".documentation-card")).toHaveCount(8);
    await expect(catalog).toHaveAttribute("data-open", "true");
    await captureThemes("documentation-catalog");

    await page.setViewportSize({ width: 400, height: 900 });
    for (const theme of ["light", "dark"] as const) {
      await setTheme(theme);
      if ((await catalog.getAttribute("data-open")) !== "true")
        await catalog.getByRole("button", { name: /Explorar guías/ }).click();
      await catalog
        .getByRole("button", { name: "1. Normalización", exact: true })
        .click();
      const normalizationGuide = page.getByRole("article", {
        name: "1. Normalización",
        exact: true,
      });
      await expect(normalizationGuide).toBeFocused();
      await expect(catalog).toHaveAttribute("data-open", "false");
      await expect(
        catalog.locator(".documentation-catalog-content"),
      ).toBeHidden();
      const exploreGuides = catalog.getByRole("button", {
        name: /Explorar guías/,
      });
      await expect(exploreGuides).toHaveAttribute("aria-expanded", "false");
      await exploreGuides.click();
      await expect(catalog).toHaveAttribute("data-open", "true");
      await expect(
        catalog.locator(".documentation-catalog-content"),
      ).toBeVisible();
      await catalog
        .getByRole("button", {
          name: "2. Procedimiento de puerta",
          exact: true,
        })
        .click();
      await expect(
        page.getByRole("article", {
          name: "2. Procedimiento de puerta",
          exact: true,
        }),
      ).toBeFocused();
      await expect(catalog).toHaveAttribute("data-open", "false");
      await expect(
        catalog.locator(".documentation-catalog-content"),
      ).toBeHidden();
      expect(
        await page.evaluate(
          () => document.documentElement.scrollWidth <= window.innerWidth,
        ),
      ).toBe(true);
      await capture(`mobile-documentation-reader-${theme}`);
    }
    await page.setViewportSize({ width: 1440, height: 1000 });
    await setTheme("light");
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
    await setTheme("dark");
    await assertRenderedReferencePoint(page);
    await page
      .getByRole("button", { name: "Abrir navegación", exact: true })
      .click();
    await expect(drawer).toBeVisible();
    await expect(
      drawer.getByRole("link", { name: "Auditoría", exact: true }),
    ).toHaveCount(0);
    await page.screenshot({
      path: resolve(artifacts, "ui-modules-mobile-menu-dark.png"),
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
  // Inspect the actual WebGL image, using the same theme color as the legend.
  // Canvas existence or an idle frame alone cannot prove the point was painted.
  await expect
    .poll(
      async () => {
        const color = await page
          .locator(".statistics-content")
          .evaluate((element) =>
            getComputedStyle(element)
              .getPropertyValue("--statistics-reference")
              .trim(),
          );
        if (!color) return 0;
        const buffer = await page
          .locator(".statistics-map-canvas canvas")
          .screenshot();
        return page.evaluate(
          async ({ bytes, color }) => {
            const swatch = document.createElement("canvas");
            swatch.width = swatch.height = 1;
            const sample = swatch.getContext("2d")!;
            sample.fillStyle = color;
            sample.fillRect(0, 0, 1, 1);
            const expected = sample.getImageData(0, 0, 1, 1).data;
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
                Math.abs(data[i] - expected[0]) <= 5 &&
                Math.abs(data[i + 1] - expected[1]) <= 5 &&
                Math.abs(data[i + 2] - expected[2]) <= 5
              )
                pixels++;
            bitmap.close();
            return pixels;
          },
          { bytes: Array.from(buffer), color },
        );
      },
      { timeout: 15000, intervals: [200, 500, 1000] },
    )
    .toBeGreaterThan(20);
}
