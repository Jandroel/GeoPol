import { test, expect } from "@playwright/test";
import { mkdir } from "node:fs/promises";
import { resolve } from "node:path";

test("base reference, unconfirmed source CRS and explicit equivalent review work together", async ({
  page,
}) => {
  const username = process.env.GEOPOL_E2E_USER;
  const password = process.env.GEOPOL_E2E_PASSWORD;
  test.skip(!username || !password, "Provide isolated synthetic credentials.");
  const artifacts = resolve(
    process.env.GEOPOL_E2E_ARTIFACTS ?? resolve(process.cwd(), "..", ".local"),
  );
  await mkdir(artifacts, { recursive: true });
  async function capture(filename: string) {
    await page.evaluate(async () => {
      await document.fonts.ready;
      window.scrollTo(0, 0);
    });
    await page.locator(".page-heading h1").click();
    await page.evaluate(() => window.scrollTo(0, 0));
    await page.screenshot({
      path: resolve(artifacts, filename),
      fullPage: true,
      animations: "disabled",
    });
  }
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await page.goto("/");
  await page.getByLabel("Usuario", { exact: true }).fill(username!);
  await page.getByLabel("Contraseña", { exact: true }).fill(password!);
  await page
    .getByRole("button", { name: "Ingresar al espacio de trabajo" })
    .click();
  await expect(page.getByRole("heading", { name: "Resumen" })).toBeVisible();
  const token = await page.evaluate(() =>
    sessionStorage.getItem("geopol.session"),
  );
  const headers = { Authorization: `Bearer ${token}` };
  const oldDefaultsResponse = await page.request.get(
    "/api/processing-defaults",
    { headers },
  );
  expect(oldDefaultsResponse.status()).toBe(200);
  const oldDefaults = await oldDefaultsResponse.json();
  const catalogName = `QA automatización ${Date.now()}`;
  const reference = await page.request.post("/api/references", {
    headers,
    multipart: {
      name: catalogName,
      version: "automation-qa",
      source: "SINTÉTICO: revisión equivalente y referencia base",
      file: {
        name: "reference.geojson",
        mimeType: "application/geo+json",
        buffer: Buffer.from(
          JSON.stringify({
            type: "FeatureCollection",
            features: [
              {
                type: "Feature",
                properties: {
                  id: "door",
                  kind: "door",
                  ubigeo: "150101",
                  street_type: "AVENIDA",
                  street_name: "DEMOSTRACION",
                  door_number: "120",
                },
                geometry: { type: "Point", coordinates: [-77.03, -12.04] },
              },
              {
                type: "Feature",
                properties: {
                  id: "boundary",
                  kind: "boundary",
                  ubigeo: "150101",
                },
                geometry: {
                  type: "Polygon",
                  coordinates: [
                    [
                      [-78, -13],
                      [-76, -13],
                      [-76, -11],
                      [-78, -11],
                      [-78, -13],
                    ],
                  ],
                },
              },
            ],
          }),
        ),
      },
    },
  });
  expect(reference.status()).toBe(201);
  const catalog = await reference.json();
  try {
    await page.goto("/references");
    await page
      .locator(".reference-card")
      .filter({
        has: page.getByRole("heading", { name: catalogName, exact: true }),
      })
      .getByRole("button", { name: "Usar como referencia base" })
      .click();
    await expect(page.getByText(/Referencia base configurada/)).toBeVisible();
    await page.goto("/runs/new");
    await page.locator("#source-file").setInputFiles({
      name: "automation-synthetic.csv",
      mimeType: "text/csv",
      buffer: Buffer.from(
        "complaint_id,location_original,ubigeo\nGROUP-001,AV DEMOSTRACIOZ 120,150101\nGROUP-002,AV DEMOSTRACIOZ 120,150101\nAUTO-001,AV DEMOSTRACION 120,150101\n",
      ),
    });
    await page
      .getByRole("button", { name: "Cargar y verificar columnas" })
      .click();
    await expect(page.getByLabel("Catálogo de referencia")).toHaveValue(
      "default",
    );
    await expect(
      page.getByLabel("Sistema de coordenadas originales"),
    ).toHaveValue("unconfirmed");
    await capture("ui-automation-configuration.png");
    const createdResponse = page.waitForResponse(
      (response) =>
        response.url().endsWith("/api/runs") &&
        response.request().method() === "POST",
    );
    await page.getByRole("button", { name: "Iniciar procesamiento" }).click();
    const created = await (await createdResponse).json();
    expect(created.reference_id).toBe(catalog.id);
    expect(created.config.crs).toBeNull();
    expect(created.config.crs_evidence).toBeNull();
    await expect(page.locator(".page-heading .badge")).toHaveText(
      "Completado",
      { timeout: 120000 },
    );
    const results = await page.request.get(`/api/runs/${created.id}/results`, {
      headers,
    });
    const items = (await results.json()).items;
    expect(
      items.find(
        (item: { complaint_id: string }) => item.complaint_id === "AUTO-001",
      ).resolution,
    ).toBe("ACEPTADO_AUTOMATICO");
    const group = items.filter((item: { complaint_id: string }) =>
      item.complaint_id.startsWith("GROUP-"),
    );
    expect(group).toHaveLength(2);
    expect(
      group.every(
        (item: { review_bucket: string }) =>
          item.review_bucket === "actionable",
      ),
    ).toBe(true);
    await capture("ui-automation-readiness.png");
    const previousDetails = new Map(
      await Promise.all(
        group.map(async (item: { id: string }) => {
          const previous = await (
            await page.request.get(`/api/results/${item.id}`, { headers })
          ).json();
          expect(previous.history).toHaveLength(1);
          expect(previous.history[0]).toMatchObject({
            action: "automatic_resolution",
            revision: 1,
          });
          return [item.id, previous] as const;
        }),
      ),
    );
    await page.goto(`/results/${group[0].id}`);
    await page.getByRole("button", { name: "Buscar equivalentes" }).click();
    const apply = page.getByRole("button", {
      name: "Aplicar decisión a 2 ubicaciones",
    });
    await expect(apply).toBeDisabled();
    const common = page.getByLabel("Candidato para el grupo");
    await common.selectOption({ index: 1 });
    await page
      .getByLabel("Motivo de la decisión conjunta")
      .fill(
        "Verificación sintética de ambas direcciones contra el catálogo y límite de prueba.",
      );
    await expect(apply).toBeDisabled();
    await page
      .getByRole("checkbox", { name: /He revisado el candidato/ })
      .check();
    await expect(page.locator(".maplibregl-canvas")).toBeVisible();
    await expect(page.getByText("Preparando visor espacial…")).toHaveCount(0);
    await expect(page.locator(".map-caption")).toContainText(
      "Contexto local del catálogo",
    );
    await capture("ui-equivalent-preview.png");
    await page.setViewportSize({ width: 400, height: 900 });
    await expect(apply).toBeEnabled();
    // MapLibre resizes its canvas on the next animation frame after a viewport
    // change. Check the settled layout rather than the old desktop canvas.
    await expect
      .poll(() =>
        page.evaluate(
          () => document.documentElement.scrollWidth <= window.innerWidth,
        ),
      )
      .toBe(true);
    await capture("ui-equivalent-preview-mobile.png");
    await page.setViewportSize({ width: 1440, height: 1000 });
    const decisionResponse = page.waitForResponse(
      (response) =>
        response
          .url()
          .endsWith(`/api/results/${group[0].id}/review-group/decide`) &&
        response.request().method() === "POST",
    );
    await apply.click();
    const decision = await (await decisionResponse).json();
    expect(decision.group_id).toEqual(expect.any(String));
    expect(decision.applied_count).toBe(2);
    await expect(
      page.getByText(/Decisión registrada en 2 ubicaciones equivalentes/),
    ).toBeVisible();
    for (const item of group) {
      const updated = await (
        await page.request.get(`/api/results/${item.id}`, { headers })
      ).json();
      expect(updated.resolution).toBe("ACEPTADO_MANUAL");
      expect(updated.review_status).toBe("CLOSED");
      const previous = previousDetails.get(item.id)!;
      expect(updated.revision).toBe(previous.revision + 1);
      expect(updated.history).toHaveLength(2);
      expect(
        updated.history.map((revision: { action: string }) => revision.action),
      ).toEqual(["accept_candidate", "automatic_resolution"]);
      expect(
        updated.history.map(
          (revision: { revision: number }) => revision.revision,
        ),
      ).toEqual([2, 1]);
      expect(updated.history[1]).toEqual(previous.history[0]);
      expect(updated.normalized.review_group.id).toBe(decision.group_id);
      expect(updated.history[0].snapshot.review_group_id).toBe(
        decision.group_id,
      );
    }
    expect(errors).toEqual([]);
  } finally {
    const restored = await page.request.put("/api/processing-defaults", {
      headers,
      data: { reference_id: oldDefaults.default_reference_id },
    });
    expect(restored.status()).toBe(200);
  }
});
