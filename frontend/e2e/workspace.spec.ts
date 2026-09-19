import { test, expect } from "@playwright/test";
import { mkdir, readFile } from "node:fs/promises";
import { resolve } from "node:path";

const username = process.env.GEOPOL_E2E_USER;
const password = process.env.GEOPOL_E2E_PASSWORD;
const artifacts = resolve(process.cwd(), "..", ".local");
const examples = resolve(process.cwd(), "..", "examples");

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
