import { test, expect, type Page } from "@playwright/test";
import { mkdir } from "node:fs/promises";
import { resolve } from "node:path";

test("synthetic geometry renders in WebGL and explicit address reuse can be revoked", async ({
  page,
}) => {
  const username = process.env.GEOPOL_E2E_USER;
  const password = process.env.GEOPOL_E2E_PASSWORD;
  test.skip(!username || !password, "Provide isolated synthetic credentials.");
  const artifacts = resolve(
    process.env.GEOPOL_E2E_ARTIFACTS ?? resolve(process.cwd(), "..", ".local"),
  );
  await mkdir(artifacts, { recursive: true });
  const browserErrors: string[] = [];
  const externalRequests: string[] = [];
  const origin = new URL(process.env.GEOPOL_E2E_URL ?? "http://127.0.0.1:5174")
    .origin;
  page.on("pageerror", (error) => browserErrors.push(error.message));
  page.on("console", (message) => {
    if (message.type() === "error") browserErrors.push(message.text());
  });
  page.on("request", (request) => {
    if (
      /^https?:/.test(request.url()) &&
      new URL(request.url()).origin !== origin
    )
      externalRequests.push(request.url());
  });
  await page.goto("/");
  await page.getByLabel("Usuario", { exact: true }).fill(username!);
  await page.getByLabel("Contraseña", { exact: true }).fill(password!);
  await page
    .getByRole("button", { name: "Ingresar al espacio de trabajo" })
    .click();
  await expect(page.getByLabel("Contraseña", { exact: true })).toHaveCount(0);
  await expect(page.getByRole("heading", { name: "Resumen" })).toBeVisible();
  const token = await page.evaluate(() =>
    sessionStorage.getItem("geopol.session"),
  );
  expect(token).toBeTruthy();
  const headers = { Authorization: `Bearer ${token}` };
  const geometry = {
    type: "LineString",
    coordinates: [
      [-77.045, -12.048],
      [-77.035, -12.045],
      [-77.028, -12.033],
    ],
  };
  const polygon = {
    type: "Polygon",
    coordinates: [
      [
        [-77.045, -12.048],
        [-77.028, -12.048],
        [-77.028, -12.033],
        [-77.045, -12.033],
        [-77.045, -12.048],
      ],
    ],
  };
  const reference = await page.request.post("/api/references", {
    headers,
    multipart: {
      name: "QA geometría sintética",
      version: "browser-geometry-1",
      source: "SINTÉTICO · simulación de procedencia OpenStreetMap",
      file: {
        name: "geometria-sintetica.geojson",
        mimeType: "application/geo+json",
        buffer: Buffer.from(
          JSON.stringify({
            type: "FeatureCollection",
            features: [
              {
                type: "Feature",
                id: "qa-boundary",
                properties: {
                  kind: "boundary",
                  ubigeo: "150101",
                  name: "LÍMITE SINTÉTICO",
                },
                geometry: {
                  type: "Polygon",
                  coordinates: [
                    [
                      [-77.06, -12.06],
                      [-77.02, -12.06],
                      [-77.02, -12.02],
                      [-77.06, -12.02],
                      [-77.06, -12.06],
                    ],
                  ],
                },
              },
              {
                type: "Feature",
                id: "qa-line",
                properties: {
                  kind: "street",
                  ubigeo: "150101",
                  street_type: "CALLE",
                  street_name: "ENSAYO VECTORIAL",
                  name: "TRAMO SINTÉTICO",
                },
                geometry,
              },
              {
                type: "Feature",
                id: "qa-polygon",
                properties: {
                  kind: "site",
                  ubigeo: "150101",
                  name: "PARQUE ENSAYO POLIGONAL",
                },
                geometry: polygon,
              },
            ],
          }),
        ),
      },
    },
  });
  expect(reference.status()).toBe(201);
  const catalog = await reference.json();

  async function createRun(
    complaint: string,
    referenceId: string | null,
    site = false,
  ) {
    const data = Buffer.from(
      site
        ? `complaint_id,location_original,ubigeo\n${complaint},PARQUE ENSAYO POLIGONAL,150101\n`
        : `complaint_id,location_original,ubigeo,street_type,street_name\n${complaint},CALLE ENSAYO VECTORIAL,150101,CALLE,ENSAYO VECTORIAL\n`,
    );
    const uploadResponse = await page.request.post("/api/uploads", {
      headers,
      data: { filename: "geometria-sintetica.csv", size: data.length },
    });
    expect(uploadResponse.status()).toBe(201);
    const upload = await uploadResponse.json();
    expect(
      (
        await page.request.patch(`/api/uploads/${upload.id}`, {
          headers: {
            ...headers,
            "Upload-Offset": "0",
            "Content-Type": "application/octet-stream",
          },
          data,
        })
      ).status(),
    ).toBe(200);
    expect(
      (
        await page.request.post(`/api/uploads/${upload.id}/complete`, {
          headers,
        })
      ).status(),
    ).toBe(200);
    const started = await page.request.post("/api/runs", {
      headers,
      data: {
        upload_id: upload.id,
        name: `QA geometría ${complaint}`,
        reference_id: referenceId,
        crs: "EPSG:4326",
        crs_evidence:
          "Metadatos de fixture sintética: coordenadas WGS84 EPSG:4326",
      },
    });
    expect(started.status()).toBe(201);
    const run = await started.json();
    let status = "";
    await expect
      .poll(
        async () => {
          const current = await page.request.get(`/api/runs/${run.id}`, {
            headers,
          });
          expect(current.status()).toBe(200);
          status = (await current.json()).status;
          return [
            "COMPLETED",
            "COMPLETED_WITH_ISSUES",
            "FAILED",
            "CANCELLED",
          ].includes(status);
        },
        { timeout: 90000, intervals: [200, 500, 1000] },
      )
      .toBe(true);
    expect(status).toBe("COMPLETED");
    const results = await page.request.get(`/api/runs/${run.id}/results`, {
      headers,
    });
    expect(results.status()).toBe(200);
    const items = (await results.json()).items;
    expect(items).toHaveLength(1);
    return { runId: run.id, item: items[0] };
  }

  const first = await createRun("QA-GEOMETRIA-A", catalog.id);
  expect(first.item).toMatchObject({
    resolution: "ACEPTADO_AUTOMATICO",
    product: "AREA_TRAMO",
    precision: "VIA",
    latitude: null,
    longitude: null,
    geometry,
  });
  await page.goto(`/runs/${first.runId}`);
  await expect(
    page
      .locator(".automatic-summary > div")
      .filter({ hasText: "Automáticas con área o tramo" })
      .locator("strong"),
  ).toHaveText("1");
  await expect(
    page
      .locator(".automatic-summary > div")
      .filter({ hasText: "Automáticas con punto" })
      .locator("strong"),
  ).toHaveText("0");
  await page.goto(`/results/${first.item.id}`);
  await expect(
    page.getByText(
      /La ubicación se representa mediante su geometría de referencia/,
    ),
  ).toBeVisible();
  await expect(page.locator(".maplibregl-canvas")).toBeVisible();
  await expect(page.locator(".maplibregl-marker")).toHaveCount(0);
  await expect(
    page.getByRole("link", { name: "OpenStreetMap contributors" }),
  ).toHaveAttribute("href", "https://www.openstreetmap.org/copyright");
  await page
    .locator(".map-panel")
    .screenshot({ path: resolve(artifacts, "ui-geometry-map.png") });
  await assertRenderedGeometry(page);

  await page
    .getByRole("button", { name: "Tomar revisión", exact: true })
    .click();
  await expect(page.getByLabel("Acción", { exact: true })).toHaveValue(
    "reopen",
  );
  await page
    .getByLabel("Motivo de la decisión")
    .fill("QA sintética: comprobar validación explícita de la geometría.");
  await page
    .getByRole("button", { name: "Registrar decisión", exact: true })
    .click();
  await expect(page.locator(".review-stage")).toHaveText("Pendiente");
  await page
    .getByRole("button", { name: "Tomar revisión", exact: true })
    .click();
  await page.getByLabel("Candidato", { exact: true }).selectOption("qa-line");
  const consent = page.getByLabel(
    "Reutilizar esta dirección validada en futuros lotes",
  );
  await expect(consent).not.toBeChecked();
  await consent.check();
  await page
    .getByLabel("Motivo de la decisión")
    .fill(
      "QA sintética: tramo contrastado y autorizado para coincidencias exactas futuras.",
    );
  await page
    .getByRole("button", { name: "Registrar decisión", exact: true })
    .click();
  await expect(
    page.getByText(
      "Decisión registrada. La revisión anterior se conserva en el historial.",
    ),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: "Desactivar reutilización" }),
  ).toBeVisible();

  const second = await createRun("QA-GEOMETRIA-B", null);
  expect(second.item).toMatchObject({
    resolution: "ACEPTADO_AUTOMATICO",
    method: "DIRECCION_VALIDADA",
    product: "AREA_TRAMO",
    latitude: null,
    longitude: null,
    geometry,
  });
  await page.goto(`/results/${second.item.id}`);
  await expect(
    page.getByRole("link", { name: "OpenStreetMap contributors" }),
  ).toBeVisible();
  await expect(
    page.getByText(
      /Resultado procedente de una dirección validada previamente/,
    ),
  ).toBeVisible();
  await page.setViewportSize({ width: 400, height: 900 });
  await assertRenderedGeometry(page);
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBe(true);
  await page
    .locator(".map-panel")
    .screenshot({ path: resolve(artifacts, "ui-geometry-map-mobile.png") });
  await page.getByRole("button", { name: "Desactivar reutilización" }).click();
  await expect(
    page.getByText("Reutilización desactivada", { exact: true }),
  ).toBeVisible();
  const third = await createRun("QA-GEOMETRIA-C", null);
  expect(third.item.resolution).not.toBe("ACEPTADO_AUTOMATICO");
  const historical = await page.request.get(`/api/results/${second.item.id}`, {
    headers,
  });
  expect(await historical.json()).toMatchObject({
    resolution: "ACEPTADO_AUTOMATICO",
    geometry,
  });
  const park = await createRun("QA-GEOMETRIA-POLIGONO", catalog.id, true);
  expect(park.item).toMatchObject({
    resolution: "ACEPTADO_AUTOMATICO",
    product: "AREA_TRAMO",
    precision: "SITIO",
    latitude: null,
    longitude: null,
    geometry: polygon,
  });
  await page.setViewportSize({ width: 1440, height: 1000 });
  await page.goto(`/results/${park.item.id}`);
  await expect(page.locator(".maplibregl-canvas")).toBeVisible();
  await expect(page.locator(".maplibregl-marker")).toHaveCount(0);
  await assertRenderedGeometry(page);
  await page.locator(".map-panel").screenshot({
    path: resolve(artifacts, "ui-geometry-polygon.png"),
  });
  expect(browserErrors).toEqual([]);
  expect(externalRequests).toEqual([]);
});

async function assertRenderedGeometry(page: Page) {
  // Check pixels from the real WebGL canvas, not a mock or hidden map instance.
  // The blank background and navigation controls cannot satisfy this blue stroke threshold.
  await expect
    .poll(
      async () => {
        const buffer = await page.locator(".map-canvas").screenshot();
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
              data[i] < 70 &&
              data[i + 1] > 25 &&
              data[i + 1] < 105 &&
              data[i + 2] > 75 &&
              data[i + 2] < 145
            )
              pixels++;
          bitmap.close();
          return pixels;
        }, Array.from(buffer));
      },
      { timeout: 15000, intervals: [200, 500, 1000] },
    )
    .toBeGreaterThan(200);
}
