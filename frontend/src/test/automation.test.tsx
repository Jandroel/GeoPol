import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { NewRun } from "../pages/NewRun";
import { EquivalentReview } from "../components/EquivalentReview";
import { ReprocessPanel } from "../components/ReprocessPanel";
import { documentedCrs } from "../components/CoordinatePolicy";
import type { ReviewGroupPreview, Run } from "../types";

vi.mock("../auth", () => ({
  useAuth: () => ({ user: { id: "synthetic-admin", role: "admin" } }),
}));
vi.mock("../lib/upload", () => ({
  getResume: () => null,
  clearResume: vi.fn(),
  uploadFile: vi.fn(async () => ({
    id: "upload-1",
    filename: "synthetic.csv",
    profile: {
      columns: ["complaint_id", "location_original"],
      sheets: [],
      suggested_mapping: {
        complaint_id: "complaint_id",
        location_original: "location_original",
      },
      warnings: [],
    },
  })),
}));
const catalog = {
  id: "ref-base",
  name: "Referencia sintética",
  version: "v1",
  source: "QA local",
  feature_count: 3,
  sha256: "synthetic",
  kinds: ["door", "boundary"],
};
function setup(element: React.ReactNode) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={["/runs/new"]}>
        <Routes>
          <Route path="/runs/new" element={element} />
          <Route
            path="/runs/run-created"
            element={<div>Procesamiento creado</div>}
          />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}
afterEach(() => vi.unstubAllGlobals());
function mockCreation(status = "ready") {
  const writes: Record<string, unknown>[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, options: RequestInit = {}) => {
      if (url.endsWith("/processing-defaults"))
        return Response.json({
          default_reference_id: status === "ready" ? catalog.id : null,
          catalog: status === "ready" ? catalog : null,
          status,
        });
      if (url.includes("/references"))
        return Response.json({
          items: [catalog],
          total: 1,
          page: 1,
          page_size: 100,
        });
      writes.push(JSON.parse(options.body as string));
      return Response.json({ id: "run-created" });
    }),
  );
  return writes;
}
async function upload() {
  const user = userEvent.setup();
  await user.upload(
    document.querySelector("#source-file")!,
    new File(["synthetic"], "synthetic.csv", { type: "text/csv" }),
  );
  fireEvent.submit(document.querySelector(".upload-panel")!);
  await screen.findByLabelText("Catálogo de referencia");
  return user;
}
describe("safe processing defaults", () => {
  it("uses the independently selected reference files once each in the quality workflow", async () => {
    const writes = mockCreation();
    setup(<NewRun />);
    const user = await upload();
    await user.selectOptions(
      screen.getByLabelText("Fuente para puertas / viviendas"),
      catalog.id,
    );
    await user.selectOptions(
      screen.getByLabelText("Fuente para límites administrativos"),
      catalog.id,
    );
    expect(screen.getByLabelText("Flujo de procesamiento")).toHaveValue(
      "quality_v1",
    );
    expect(screen.getByLabelText("Catálogo de referencia")).toBeDisabled();
    await user.click(
      screen.getByRole("button", { name: "Iniciar procesamiento" }),
    );
    await screen.findByText("Procesamiento creado");
    expect(writes[0]).toMatchObject({
      workflow: "quality_v1",
      reference_ids: [catalog.id],
      reference_id: null,
      crs: null,
    });
  });
  it("preselects the default reference while leaving original CRS unconfirmed", async () => {
    const writes = mockCreation();
    setup(<NewRun />);
    const user = await upload();
    expect(screen.getByLabelText("Catálogo de referencia")).toHaveValue(
      "default",
    );
    expect(
      screen.getByLabelText("Sistema de coordenadas originales"),
    ).toHaveValue("unconfirmed");
    expect(
      screen.getByText(/puertas, límites territoriales/),
    ).toBeInTheDocument();
    await user.click(
      screen.getByRole("button", { name: "Iniciar procesamiento" }),
    );
    await screen.findByText("Procesamiento creado");
    expect(writes).toHaveLength(1);
    expect(writes[0]).not.toHaveProperty("reference_id");
    expect(writes[0]).toMatchObject({ crs: null, crs_evidence: null });
  });
  it("requires an explicit no-reference choice when the base is unavailable", async () => {
    const writes = mockCreation("not_configured");
    setup(<NewRun />);
    const user = await upload();
    expect(
      screen.getByRole("button", { name: "Iniciar procesamiento" }),
    ).toBeDisabled();
    await user.selectOptions(
      screen.getByLabelText("Catálogo de referencia"),
      "",
    );
    await user.click(
      screen.getByRole("button", { name: "Iniciar procesamiento" }),
    );
    await screen.findByText("Procesamiento creado");
    expect(writes[0]).toMatchObject({ reference_id: null, crs: null });
  });
  it("only sends WGS84 with documented evidence", async () => {
    const writes = mockCreation();
    setup(<NewRun />);
    const user = await upload();
    await user.selectOptions(
      screen.getByLabelText("Sistema de coordenadas originales"),
      "EPSG:4326",
    );
    expect(
      screen.getByRole("button", { name: "Iniciar procesamiento" }),
    ).toBeDisabled();
    await user.type(
      screen.getByLabelText("Fuente de confirmación de WGS84"),
      "Metadatos de fixture sintética WGS84",
    );
    await user.click(
      screen.getByRole("button", { name: "Iniciar procesamiento" }),
    );
    await screen.findByText("Procesamiento creado");
    expect(writes[0]).toMatchObject({
      crs: "EPSG:4326",
      crs_evidence: "Metadatos de fixture sintética WGS84",
    });
  });
  it("does not inherit a legacy WGS84 assumption when reprocessing", async () => {
    const writes = mockCreation();
    const run: Run = {
      id: "run-old",
      config: { crs: "EPSG:4326" },
      name: "Fixture sintética",
      status: "COMPLETED",
      filename: "synthetic.csv",
      created_at: "2026-09-22T00:00:00Z",
      source_rows: 1,
      location_units: 1,
      processed_units: 1,
      issue_rows: 0,
      rules_version: "synthetic",
      counts: {},
    };
    setup(<ReprocessPanel run={run} />);
    await waitFor(() =>
      expect(
        screen.getByRole("button", { name: "Crear nuevo procesamiento" }),
      ).toBeEnabled(),
    );
    expect(
      screen.getByLabelText("Sistema de coordenadas originales"),
    ).toHaveValue("unconfirmed");
    expect(screen.getByText(/no heredará esa suposición/)).toBeInTheDocument();
    await userEvent
      .setup()
      .click(screen.getByRole("button", { name: "Crear nuevo procesamiento" }));
    await screen.findByText("Procesamiento creado");
    expect(writes[0]).toMatchObject({
      reference_id: "ref-base",
      crs: null,
      crs_evidence: null,
    });
    expect(
      documentedCrs({
        crs: "EPSG:4326",
        crs_evidence: "Metadatos documentados",
      }),
    ).toBe(true);
  });
});
const group: ReviewGroupPreview = {
  base_id: "loc-1",
  run_id: "run-1",
  eligible: true,
  reason: null,
  token: "preview-v1",
  count: 2,
  source_rows: 4,
  limit: 200,
  truncated: false,
  excluded_count: 1,
  members: [1, 2].map((id) => ({
    id: `loc-${id}`,
    complaint_id: `QA-${id}`,
    location_normalized: "CALLE PRUEBA 10",
    ubigeo: "150101",
    revision: 1,
    source_row_count: 2,
  })),
  candidates: [
    {
      id: "candidate-1",
      label: "Puerta de prueba",
      precision: "PUERTA",
      method: "EXACT",
      source: "QA",
      version: "v1",
    },
  ],
};
describe("equivalent review confirmation", () => {
  it("requires preview, candidate, reason and explicit scope confirmation before a group decision", async () => {
    const saved = vi.fn(async () => {});
    const writes: unknown[] = [];
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string, options: RequestInit = {}) => {
        if (url.endsWith("/preview")) return Response.json(group);
        writes.push(JSON.parse(options.body as string));
        return Response.json({ applied_count: 2 });
      }),
    );
    setup(<EquivalentReview resultId="loc-1" onSaved={saved} />);
    const user = userEvent.setup();
    expect(writes).toHaveLength(0);
    await user.click(
      screen.getByRole("button", { name: "Buscar equivalentes" }),
    );
    const apply = await screen.findByRole("button", {
      name: "Aplicar decisión a 2 ubicaciones",
    });
    expect(apply).toBeDisabled();
    expect(screen.getByText("QA-2")).toBeInTheDocument();
    await user.selectOptions(
      screen.getByLabelText("Candidato para el grupo"),
      "candidate-1",
    );
    await user.type(
      screen.getByLabelText("Motivo de la decisión conjunta"),
      "Comprobadas ambas ubicaciones con evidencia sintética",
    );
    expect(apply).toBeDisabled();
    await user.click(screen.getByRole("checkbox"));
    await user.click(apply);
    await waitFor(() => expect(saved).toHaveBeenCalledOnce());
    expect(writes).toEqual([
      {
        token: "preview-v1",
        candidate_id: "candidate-1",
        reason: "Comprobadas ambas ubicaciones con evidencia sintética",
      },
    ]);
  });
  it("invalidates a stale preview and requires checking a refreshed scope after a conflict", async () => {
    let reads = 0;
    let writes = 0;
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string) => {
        if (url.endsWith("/preview")) {
          reads++;
          return Response.json(group);
        }
        writes++;
        return Response.json({ detail: "El grupo cambió" }, { status: 409 });
      }),
    );
    setup(<EquivalentReview resultId="loc-1" onSaved={vi.fn()} />);
    const user = userEvent.setup();
    await user.click(
      screen.getByRole("button", { name: "Buscar equivalentes" }),
    );
    await user.selectOptions(
      await screen.findByLabelText("Candidato para el grupo"),
      "candidate-1",
    );
    await user.type(
      screen.getByLabelText("Motivo de la decisión conjunta"),
      "Evidencia documentada sintética",
    );
    await user.click(screen.getByRole("checkbox"));
    await user.click(
      screen.getByRole("button", { name: "Aplicar decisión a 2 ubicaciones" }),
    );
    await screen.findByText(/Actualiza la vista previa/);
    expect(
      screen.getByRole("button", { name: "Aplicar decisión a 2 ubicaciones" }),
    ).toBeDisabled();
    expect(writes).toBe(1);
    await user.click(
      screen.getByRole("button", { name: "Actualizar vista previa" }),
    );
    await waitFor(() => expect(reads).toBe(2));
    expect(screen.getByRole("checkbox")).not.toBeChecked();
    expect(screen.getByLabelText("Candidato para el grupo")).toHaveValue("");
  });
  it("prevents applying an incomplete or ineligible group", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () =>
        Response.json({
          ...group,
          truncated: true,
          eligible: false,
          token: null,
        }),
      ),
    );
    setup(<EquivalentReview resultId="loc-1" onSaved={vi.fn()} />);
    await userEvent
      .setup()
      .click(screen.getByRole("button", { name: "Buscar equivalentes" }));
    await screen.findByText(/No se permite aplicar una selección incompleta/);
    expect(
      screen.queryByRole("button", { name: /Aplicar decisión/ }),
    ).not.toBeInTheDocument();
  });
});
