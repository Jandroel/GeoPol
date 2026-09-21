import { test, expect } from "@playwright/test";
import { mkdir, readFile } from "node:fs/promises";
import { resolve } from "node:path";

const username = process.env.GEOPOL_E2E_USER;
const password = process.env.GEOPOL_E2E_PASSWORD;
const artifacts = resolve(
  process.env.GEOPOL_E2E_ARTIFACTS ?? resolve(process.cwd(), "..", ".local"),
);
const examples = resolve(process.cwd(), "..", "examples");

test("review prerequisites, reference reprocessing, save-next and finalization", async ({
  page,
}) => {
  test.skip(
    !username || !password,
    "Provide synthetic credentials for an isolated environment.",
  );
  const browserErrors: string[] = [];
  page.on("pageerror", (error) => browserErrors.push(error.message));
  page.on("console", (message) => {
    if (message.type() === "error") browserErrors.push(message.text());
  });
  const marker = Date.now().toString();
  const catalogName = `QA revisión catálogo ${marker}`;
  const runName = `QA revisión dos ubicaciones ${marker}`;
  await mkdir(artifacts, { recursive: true });
  await page.goto("/");
  await page.getByLabel("Usuario", { exact: true }).fill(username!);
  await page.getByLabel("Contraseña", { exact: true }).fill(password!);
  await page
    .getByRole("button", { name: "Ingresar al espacio de trabajo" })
    .click();
  await expect(
    page.getByRole("heading", { name: "Una mirada a tu territorio" }),
  ).toBeVisible();

  await test.step("Prepare a documented reference and process without attaching it", async () => {
    await page.getByRole("link", { name: "Catálogos de referencia" }).click();
    await page
      .getByRole("button", { name: "Importar catálogo", exact: true })
      .click();
    await page.getByLabel("Nombre", { exact: true }).fill(catalogName);
    await page.getByLabel("Versión", { exact: true }).fill("review-qa");
    await page
      .getByLabel("Fuente y procedencia")
      .fill("SINTÉTICO: prueba aislada del flujo de revisión");
    await page
      .getByLabel("Archivo CSV o GeoJSON")
      .setInputFiles(resolve(examples, "referencias_sinteticas.geojson"));
    await page
      .getByRole("button", { name: "Importar y verificar catálogo" })
      .click();
    await expect(
      page.getByRole("heading", { name: catalogName, exact: true }),
    ).toBeVisible();
    await page.goto("/runs/new");
    await page
      .locator("#source-file")
      .setInputFiles({
        name: "revision-sintetica.csv",
        mimeType: "text/csv",
        buffer: Buffer.from(
          "complaint_id,location_original,ubigeo,street_type,street_name,door_number\nQA-REV-1,CALLE AMBIGUA 50,150101,CALLE,AMBIGUA,50\nQA-REV-2,CALLE AMBIGUA 50,150101,CALLE,AMBIGUA,50\n",
        ),
      });
    await page
      .getByRole("button", { name: "Cargar y verificar columnas" })
      .click();
    await page.getByLabel("Nombre del procesamiento").fill(runName);
    await page.getByLabel("Catálogo de referencia").selectOption("");
    await page.getByRole("button", { name: "Iniciar procesamiento" }).click();
    await expect(
      page.getByRole("heading", { name: runName, exact: true }),
    ).toBeVisible();
    await expect(page.locator(".page-heading .badge")).toHaveText(
      /Completado|Con incidencias|Fallido|Cancelado/,
      { timeout: 120000 },
    );
    expect(await page.locator(".page-heading .badge").innerText()).toBe(
      "Completado",
    );
  });
  const parentRunUrl = page.url();
  const parentId = new URL(parentRunUrl).pathname.split("/").at(-1)!;
  await test.step("Missing references are visible but not presented as actionable decisions", async () => {
    await page
      .getByRole("link", { name: "Abrir revisión de esta ejecución" })
      .click();
    await expect(
      page.getByRole("heading", {
        name: "No hay pendientes en esta selección",
      }),
    ).toBeVisible();
    await expect(
      page.getByRole("button", { name: /Referencia pendiente/ }),
    ).toContainText("2");
    await page.getByRole("button", { name: /Referencia pendiente/ }).click();
    await expect(
      page.getByText(/Estos registros necesitan una fuente evaluable/),
    ).toBeVisible();
    await expect(
      page.getByRole("link", { name: "Examinar", exact: true }),
    ).toHaveCount(2);
    await page.screenshot({
      path: resolve(artifacts, "ui-review-prerequisites.png"),
      fullPage: true,
    });
    await page
      .getByRole("link", { name: "Examinar", exact: true })
      .first()
      .click();
    await expect(
      page.getByText(/Falta una referencia evaluable/),
    ).toBeVisible();
    await expect(
      page.getByRole("button", { name: "Tomar revisión", exact: true }),
    ).not.toBeVisible();
    await page
      .getByRole("button", {
        name: "Preparar nuevo procesamiento",
        exact: true,
      })
      .click();
  });
  let currentId = "";
  await test.step("Reprocessing selects the reference while preserving the former execution", async () => {
    await page
      .getByLabel("Catálogo del nuevo procesamiento")
      .selectOption({ label: `${catalogName} · review-qa` });
    await page
      .getByRole("button", { name: "Crear nuevo procesamiento", exact: true })
      .click();
    await expect(page).not.toHaveURL(new RegExp(`${parentId}(?:\\?|$)`));
    await expect(page.locator(".page-heading .badge")).toHaveText(
      /Completado|Con incidencias|Fallido|Cancelado/,
      { timeout: 120000 },
    );
    expect(await page.locator(".page-heading .badge").innerText()).toBe(
      "Completado",
    );
    currentId = new URL(page.url()).pathname.split("/").at(-1)!;
    await page.goto(parentRunUrl);
    await expect(
      page.getByText(/Esta ejecución se conserva como histórico/),
    ).toBeVisible();
    await page
      .getByRole("link", { name: "Abrir la ejecución que la sustituye" })
      .click();
    await page
      .getByRole("link", { name: "Abrir revisión de esta ejecución" })
      .click();
    await expect(
      page.getByRole("button", { name: /Revisión accionable/ }),
    ).toContainText("2");
    await page.screenshot({
      path: resolve(artifacts, "ui-review-queue.png"),
      fullPage: true,
    });
  });
  await test.step("Save-next persists the first decision and opens a clean, unclaimed second record", async () => {
    await page
      .getByRole("button", { name: "Abrir siguiente disponible" })
      .click();
    const firstTitle = await page.locator("h1").innerText();
    await page
      .getByRole("button", { name: "Tomar revisión", exact: true })
      .click();
    await page
      .getByLabel("Candidato", { exact: true })
      .selectOption({ index: 1 });
    await page
      .getByLabel("Motivo de la decisión")
      .fill(
        "Verificación artificial del candidato para el ensayo de revisión.",
      );
    await page
      .getByRole("button", { name: "Guardar y siguiente", exact: true })
      .click();
    await expect(page.locator("h1")).not.toHaveText(firstTitle);
    await expect(
      page.getByRole("button", { name: "Tomar revisión", exact: true }),
    ).toBeVisible();
    await expect(page.getByLabel("Motivo de la decisión")).not.toBeVisible();
    await expect(page).toHaveURL(
      new RegExp(encodeURIComponent(`run_id=${currentId}`)),
    );
    await page
      .getByRole("button", { name: "Tomar revisión", exact: true })
      .click();
    await expect(page.getByLabel("Motivo de la decisión")).toHaveValue("");
    await expect(page.getByLabel("Candidato", { exact: true })).toHaveValue("");
    await page.getByLabel("Acción", { exact: true }).selectOption("unresolved");
    await page
      .getByLabel("Motivo de la decisión")
      .fill(
        "Ensayo sintético: se finaliza sin evidencia suficiente para elegir un punto.",
      );
    await page
      .getByRole("button", { name: "Guardar y siguiente", exact: true })
      .click();
    await expect(
      page.getByText(/No quedan pendientes disponibles con estos filtros/),
    ).toBeVisible();
    await expect(page.locator(".review-stage")).toHaveText("Finalizado");
    await page.screenshot({
      path: resolve(artifacts, "ui-review-finalized.png"),
      fullPage: true,
    });
  });
  await test.step("Closed records remain inspectable and can be explicitly reopened and released", async () => {
    await page
      .getByRole("button", { name: "Tomar revisión", exact: true })
      .click();
    await expect(page.getByLabel("Acción", { exact: true })).toHaveValue(
      "reopen",
    );
    await page
      .getByLabel("Motivo de la decisión")
      .fill(
        "Ensayo sintético: se solicita una verificación adicional documentada.",
      );
    await page
      .getByRole("button", { name: "Registrar decisión", exact: true })
      .click();
    await expect(page.locator(".review-stage")).toHaveText("Pendiente");
    await page
      .getByRole("button", { name: "Tomar revisión", exact: true })
      .click();
    await page
      .getByRole("button", { name: "Volver y liberar reserva", exact: true })
      .click();
    await expect(
      page.getByRole("heading", {
        name: "Revisión de ubicaciones",
        exact: true,
      }),
    ).toBeVisible();
    await expect(page.getByText("Sin reserva", { exact: true })).toBeVisible();
    await page.setViewportSize({ width: 400, height: 900 });
    await page.screenshot({
      path: resolve(artifacts, "ui-review-mobile.png"),
      fullPage: true,
    });
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= window.innerWidth,
      ),
    ).toBe(true);
    await page.getByRole("button", { name: /Finalizados: 1/ }).click();
    await expect(
      page.getByRole("link", { name: "Examinar", exact: true }),
    ).toHaveCount(1);
    await page.getByRole("link", { name: "Examinar", exact: true }).click();
    await expect(page.locator(".review-stage")).toHaveText("Finalizado");
    await expect(
      page.getByRole("heading", { name: "Historial de decisiones" }),
    ).toBeVisible();
    expect(browserErrors).toEqual([]);
  });
});

test("synthetic operation: import, process, review, export and mobile navigation", async ({
  page,
}) => {
  test.skip(
    !username || !password,
    "Set GEOPOL_E2E_USER and GEOPOL_E2E_PASSWORD for an isolated synthetic environment.",
  );
  await mkdir(artifacts, { recursive: true });
  const browserErrors: string[] = [];
  const externalRequests: string[] = [];
  const baseOrigin = new URL(
    process.env.GEOPOL_E2E_URL ?? "http://127.0.0.1:5174",
  ).origin;
  page.on("pageerror", (error) => browserErrors.push(error.message));
  page.on("console", (message) => {
    if (message.type() === "error") browserErrors.push(message.text());
  });
  page.on("request", (request) => {
    if (
      /^https?:/.test(request.url()) &&
      new URL(request.url()).origin !== baseOrigin
    )
      externalRequests.push(request.url());
  });

  await test.step("Explicit authentication and dashboard", async () => {
    await page.goto("/");
    await expect(
      page.getByRole("heading", { name: "Bienvenido a GeoPol" }),
    ).toBeVisible();
    await page.screenshot({
      path: resolve(artifacts, "ui-login.png"),
      fullPage: true,
    });
    await page.getByLabel("Usuario", { exact: true }).fill(username!);
    await page.getByLabel("Contraseña", { exact: true }).fill(password!);
    await page
      .getByRole("button", { name: "Ingresar al espacio de trabajo" })
      .click();
    await expect(
      page.getByRole("heading", { name: "Una mirada a tu territorio" }),
    ).toBeVisible();
    await page.screenshot({
      path: resolve(artifacts, "ui-dashboard.png"),
      fullPage: false,
    });
  });

  const marker = Date.now().toString();
  const catalogName = `QA catálogo sintético ${marker}`;
  const runName = `QA navegador sintético ${marker}`;
  await test.step("Import a versioned synthetic GeoJSON reference", async () => {
    await page.getByRole("link", { name: "Catálogos de referencia" }).click();
    await page
      .getByRole("button", { name: "Importar catálogo", exact: true })
      .click();
    await page.getByLabel("Nombre", { exact: true }).fill(catalogName);
    await page.getByLabel("Versión", { exact: true }).fill("qa-1");
    await page
      .getByLabel("Fuente y procedencia")
      .fill("SINTÉTICO · verificación automatizada, sin uso operativo");
    await page
      .getByLabel("Archivo CSV o GeoJSON")
      .setInputFiles(resolve(examples, "referencias_sinteticas.geojson"));
    await page
      .getByRole("button", { name: "Importar y verificar catálogo" })
      .click();
    await expect(
      page.getByText(
        "Catálogo importado. Ya puedes seleccionarlo al crear un procesamiento.",
      ),
    ).toBeVisible();
    await expect(
      page.getByRole("heading", { name: catalogName, exact: true }),
    ).toBeVisible();
  });

  let runUrl = "";
  await test.step("Upload and map a synthetic CSV, wait for server processing", async () => {
    await page
      .getByRole("link", { name: "Procesamientos", exact: true })
      .click();
    await page
      .getByRole("link", { name: "Nuevo procesamiento", exact: true })
      .click();
    await page
      .locator("#source-file")
      .setInputFiles(resolve(examples, "denuncias_sinteticas.csv"));
    await page
      .getByRole("button", { name: "Cargar y verificar columnas" })
      .click();
    await expect(
      page.getByRole("heading", { name: "Correspondencia de columnas" }),
    ).toBeVisible();
    await page.getByLabel("Nombre del procesamiento").fill(runName);
    await page
      .getByLabel("Catálogo de referencia")
      .selectOption({ label: `${catalogName} · qa-1` });
    await expect(page.getByLabel("Identificador de denuncia")).toHaveValue(
      "complaint_id",
    );
    await expect(page.getByLabel("Dirección / lugar del hecho")).toHaveValue(
      "location_original",
    );
    await page.getByRole("button", { name: "Iniciar procesamiento" }).click();
    await expect(
      page.getByRole("heading", { name: runName, exact: true }),
    ).toBeVisible();
    runUrl = page.url();
    const runStatus = page.locator(".page-heading .badge");
    await expect(runStatus).toHaveText(
      /Completado|Con incidencias|Fallido|Cancelado/,
      { timeout: 120_000 },
    );
    expect(await runStatus.innerText()).toBe("Completado");
    await expect(
      page.getByRole("row").filter({ hasText: "DEMO-010" }),
    ).toBeVisible();
    await page.screenshot({
      path: resolve(artifacts, "ui-run.png"),
      fullPage: false,
    });
    // A real reload proves state is recovered from the server, not component memory.
    await page.reload();
    await expect(page.getByText("Completado", { exact: true })).toBeVisible();
  });

  await test.step("Claim an ambiguous location and preserve its candidate decision", async () => {
    await page
      .getByRole("row")
      .filter({ hasText: "DEMO-010" })
      .getByRole("link", { name: "Examinar" })
      .click();
    await expect(
      page.getByRole("heading", { name: "DEMO-010", exact: true }),
    ).toBeVisible();
    await expect(
      page.getByRole("button", { name: "Seleccionar candidato", exact: true }),
    ).toHaveCount(2);
    await expect(page.locator(".maplibregl-marker")).toHaveCount(2);
    await expect(page.locator(".maplibregl-marker").first()).toBeVisible();
    await page.screenshot({
      path: resolve(artifacts, "ui-review.png"),
      fullPage: false,
    });
    await page
      .getByRole("button", { name: "Tomar revisión", exact: true })
      .click();
    await page
      .getByRole("combobox", { name: "Candidato", exact: true })
      .selectOption({ index: 1 });
    await page
      .getByLabel("Motivo de la decisión")
      .fill(
        "QA sintética: candidato corroborado en el catálogo artificial de referencia.",
      );
    await page.getByRole("button", { name: "Registrar decisión" }).click();
    await expect(
      page.getByText(
        "Decisión registrada. La revisión anterior se conserva en el historial.",
      ),
    ).toBeVisible();
    await expect(
      page.getByText("Aceptado por revisión", { exact: true }),
    ).toBeVisible();
    await expect(
      page.getByText(
        "QA sintética: candidato corroborado en el catálogo artificial de referencia.",
        { exact: true },
      ),
    ).toHaveCount(2);
  });

  await test.step("Generate authenticated CSV and manifest downloads", async () => {
    await page.goto(runUrl);
    await page.getByRole("tab", { name: "Exportaciones", exact: true }).click();
    await page
      .getByRole("button", { name: "Preparar exportación", exact: true })
      .click();
    const csvButton = page.getByRole("button", {
      name: "Descargar CSV",
      exact: true,
    });
    await expect(csvButton).toBeVisible({ timeout: 120_000 });
    const csvEvent = page.waitForEvent("download");
    await csvButton.click();
    const csv = await csvEvent;
    const csvPath = await csv.path();
    expect(csvPath).toBeTruthy();
    const text = await readFile(csvPath!, "utf8");
    expect(text).toContain("DEMO-010");
    expect(text).toContain("ACEPTADO_MANUAL");
    const manifestEvent = page.waitForEvent("download");
    await page
      .getByRole("button", { name: "Descargar manifiesto", exact: true })
      .click();
    const manifest = await manifestEvent;
    const manifestPath = await manifest.path();
    const data = JSON.parse(await readFile(manifestPath!, "utf8"));
    expect(data.run_id).toBe(runUrl.split("/").at(-1));
    expect(data.profile).toBe("locations");
  });

  await test.step("Mobile layout, keyboard navigation and no external geographic services", async () => {
    await page.setViewportSize({ width: 400, height: 900 });
    await page.goto("/");
    await expect(
      page.getByRole("heading", { name: "Una mirada a tu territorio" }),
    ).toBeVisible();
    await expect(
      page.getByRole("button", { name: "Abrir navegación" }),
    ).toBeVisible();
    await page.screenshot({
      path: resolve(artifacts, "ui-mobile.png"),
      fullPage: true,
    });
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= window.innerWidth,
      ),
    ).toBe(true);
    await page.keyboard.press("Tab");
    await expect(
      page.getByRole("link", { name: "Ir al contenido principal" }),
    ).toBeFocused();
    await page.keyboard.press("Tab");
    await expect(
      page.getByRole("button", { name: "Abrir navegación" }),
    ).toBeFocused();
    await page.keyboard.press("Enter");
    await expect(
      page.getByRole("link", { name: "Vista general", exact: true }),
    ).toBeFocused();
    await page.keyboard.press("Escape");
    await expect(
      page.getByRole("button", { name: "Abrir navegación" }),
    ).toBeFocused();
    await page.keyboard.press("Enter");
    await page
      .getByRole("link", { name: "Reglas y metodología", exact: true })
      .click();
    await expect(
      page.getByRole("heading", { name: "Reglas y metodología", exact: true }),
    ).toBeVisible();
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= window.innerWidth,
      ),
    ).toBe(true);
    expect(browserErrors).toEqual([]);
    expect(externalRequests).toEqual([]);
  });
});
