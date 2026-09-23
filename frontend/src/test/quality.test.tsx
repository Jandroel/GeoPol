import {
  fireEvent,
  act,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { QualityPanel } from "../components/QualityPanel";
import { ReferenceExcelCards } from "../components/ReferenceExcelCards";
import { post, request } from "../lib/api";
import { uploadFile } from "../lib/upload";
import {
  nextReviewParams,
  readReviewFilters,
  reviewParams,
} from "../lib/review";
import type { QualityOverview, Run } from "../types";

const auth = vi.hoisted(() => ({
  user: { id: "quality-user", role: "admin" },
}));
vi.mock("../auth", () => ({ useAuth: () => auth }));
vi.mock("../lib/api", () => ({
  request: vi.fn(),
  post: vi.fn(),
  downloadAuthenticated: vi.fn(),
}));
vi.mock("../lib/upload", () => ({
  uploadFile: vi.fn(),
  getResume: () => null,
  clearResume: vi.fn(),
}));
const run: Run = {
  id: "quality-run",
  name: "Sintético",
  status: "COMPLETED",
  filename: "test.xlsx",
  created_at: "2026-01-01",
  source_rows: 8,
  location_units: 4,
  processed_units: 4,
  issue_rows: 0,
  rules_version: "v1",
  counts: {},
  config: { workflow: "quality_v1" },
};
const summary: QualityOverview = {
  run_id: run.id,
  workflow: "quality_v1",
  policy_version: "quality-v1",
  provisional: false,
  totals: {
    units: 4,
    source_rows: 8,
    resolved: 1,
    review: 2,
    unmatched: 1,
    blocked: 0,
    unprocessed: 0,
  },
  qualities: [
    { code: 1, label: "Puerta exacta", units: 1, source_rows: 3 },
    { code: 2, label: "Revisión rápida", units: 1, source_rows: 2 },
    { code: 3, label: "Revisión detallada", units: 1, source_rows: 2 },
    { code: null, label: "Sin calidad", units: 1, source_rows: 1 },
  ],
  flags: [
    { flag: 1, units: 3, source_rows: 7 },
    { flag: 2, units: 0, source_rows: 0 },
    { flag: null, units: 1, source_rows: 1 },
  ],
  review_states: [
    { state: "automatic", units: 1, source_rows: 3 },
    { state: "quick_review", units: 1, source_rows: 2 },
    { state: "detailed_review", units: 1, source_rows: 2 },
    { state: "unmatched", units: 1, source_rows: 1 },
  ],
  stages: [
    {
      key: "door",
      label: "Puertas",
      units: 4,
      source_rows: 8,
      resolved: 1,
      review: 2,
      unmatched: 1,
      blocked: 0,
      percent_of_total: 100,
    },
    {
      key: "block",
      label: "Cuadras",
      units: 0,
      source_rows: 0,
      resolved: 0,
      review: 0,
      unmatched: 0,
      blocked: 0,
      percent_of_total: 0,
    },
  ],
  can_advance: true,
  next_stage: "block",
  eligible_units: 1,
  held_review_units: 2,
};
function setup(element: React.ReactNode) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 } },
  });
  render(
    <QueryClientProvider client={client}>
      <MemoryRouter>{element}</MemoryRouter>
    </QueryClientProvider>,
  );
  return userEvent.setup();
}
beforeEach(() => {
  vi.clearAllMocks();
  localStorage.clear();
  auth.user.role = "admin";
  vi.mocked(request).mockImplementation(async (path) =>
    path.endsWith("/quality")
      ? summary
      : { items: [], total: 0, page: 1, page_size: 25 },
  );
  vi.mocked(post).mockResolvedValue(run);
});
describe("quality stages", () => {
  it("explores historical chart categories without changing current-result or export filters", async () => {
    const user = setup(<QualityPanel run={run} />);
    const table = await screen.findByRole("table", {
      name: /Distribución de Puertas/,
    });
    await user.click(
      within(table).getByRole("button", { name: /Por revisar/ }),
    );
    expect(screen.getByLabelText("Flag de calidad del filtro")).toHaveValue("");
    expect(screen.getByLabelText("Estado de revisión del filtro")).toHaveValue(
      "",
    );
    expect(screen.getByLabelText("Etapa del filtro")).toHaveValue("");
    expect(
      screen.getByText("Por revisar: 2 de 4 evaluadas en esta etapa (50 %)."),
    ).toBeInTheDocument();
    await user.click(
      screen.getByRole("button", { name: "Preparar exportación" }),
    );
    await waitFor(() =>
      expect(post).toHaveBeenCalledWith(
        `/runs/${run.id}/exports`,
        expect.objectContaining({ format: "xlsx" }),
      ),
    );
    const payload = vi
      .mocked(post)
      .mock.calls.find(([path]) => path.endsWith("/exports"))?.[1];
    expect(payload).not.toHaveProperty("review_state");
    expect(payload).not.toHaveProperty("quality_stage");
    await user.selectOptions(
      screen.getByLabelText("Flag de calidad del filtro"),
      "1",
    );
    await user.selectOptions(
      screen.getByLabelText("Estado de revisión del filtro"),
      "quick_review",
    );
    await user.selectOptions(
      screen.getByLabelText("Etapa del filtro"),
      "block",
    );
    await user.click(within(table).getByRole("button", { name: /Resueltos/ }));
    expect(screen.getByLabelText("Flag de calidad del filtro")).toHaveValue(
      "1",
    );
    expect(screen.getByLabelText("Estado de revisión del filtro")).toHaveValue(
      "quick_review",
    );
    expect(screen.getByLabelText("Etapa del filtro")).toHaveValue("block");
    await user.click(
      screen.getByRole("button", { name: "Preparar exportación" }),
    );
    await waitFor(() =>
      expect(post).toHaveBeenLastCalledWith(
        `/runs/${run.id}/exports`,
        expect.objectContaining({
          quality_flag: 1,
          review_state: "quick_review",
          quality_stage: "block",
        }),
      ),
    );
  });
  it("refreshes result rows when a stage finishes between run polls without changing run status or processed count", async () => {
    let finished = false;
    vi.mocked(request).mockImplementation(async (path) => {
      if (path.endsWith("/quality"))
        return finished
          ? {
              ...summary,
              totals: { ...summary.totals, resolved: 2, unmatched: 0 },
              stages: [
                summary.stages[0],
                { ...summary.stages[1], units: 1, source_rows: 1, resolved: 1 },
              ],
            }
          : summary;
      return {
        items: [
          {
            id: "block-result",
            run_id: run.id,
            complaint_id: "QA-BLOCK-FRESH",
            location_original: "CALLE PRUEBA CUADRA 2",
            location_normalized: "CALLE PRUEBA CUADRA 2",
            ubigeo: "150101",
            resolution: finished ? "ACEPTADO_AUTOMATICO" : "SIN_COINCIDENCIA",
            quality_stage: finished ? "block" : "door",
            quality_flag: 1,
            review_state: finished ? "automatic" : "unmatched",
            precision: finished ? "CUADRA" : "DESCONOCIDA",
            product: finished ? "AREA_TRAMO" : "NINGUNO",
          },
        ],
        total: 1,
        page: 1,
        page_size: 25,
      };
    });
    const client = new QueryClient({
      defaultOptions: { queries: { retry: false, gcTime: 0 } },
    });
    render(
      <QueryClientProvider client={client}>
        <MemoryRouter>
          <QualityPanel run={run} />
        </MemoryRouter>
      </QueryClientProvider>,
    );
    // Scope the row through its unique identifier: querying every accessible
    // chart/table row can exhaust the default timeout in the parallel suite.
    const initial = (
      await screen.findByText("QA-BLOCK-FRESH", {}, { timeout: 3000 })
    ).closest("tr")!;
    expect(initial).toHaveTextContent("Sin coincidencia");
    expect(initial).toHaveTextContent("Puertas");
    finished = true;
    await act(async () => {
      await client.invalidateQueries({ queryKey: ["quality", run.id] });
    });
    await waitFor(
      () =>
        expect(
          screen.getByText("QA-BLOCK-FRESH").closest("tr"),
        ).toHaveTextContent("Aceptado automáticamente"),
      { timeout: 3000 },
    );
    const updated = screen.getByText("QA-BLOCK-FRESH").closest("tr")!;
    expect(updated).toHaveTextContent("Cuadras");
    expect(updated).not.toHaveTextContent("Sin coincidencia");
  });
  it("separates the structural flag from the review decision and does not show provisional 3/4 codes", async () => {
    const user = setup(<QualityPanel run={run} />);
    const flags = await screen.findByLabelText("Flag de calidad del filtro");
    expect(within(flags).getAllByRole("option")).toHaveLength(3);
    expect(
      within(flags).queryByRole("option", {
        name: /Revisión rápida|Flag 3|Flag 4/,
      }),
    ).not.toBeInTheDocument();
    const flagTable = screen.getByRole("table", {
      name: "Flag de calidad de las ubicaciones",
    });
    expect(
      within(flagTable).getByRole("row", { name: /Flag 1/ }),
    ).toHaveTextContent("75 %");
    await user.selectOptions(flags, "2");
    expect(
      screen.queryByRole("link", { name: "Abrir revisión rápida" }),
    ).not.toBeInTheDocument();
    await user.selectOptions(
      screen.getByLabelText("Estado de revisión del filtro"),
      "automatic",
    );
    expect(
      screen.getByRole("link", { name: "Consultar finalizados del filtro" }),
    ).toHaveAttribute("href", expect.stringContaining("stage=closed"));
  });
  it("shows stage denominators and only advances after the operator chooses the next stage", async () => {
    const user = setup(<QualityPanel run={run} />);
    const advance = await screen.findByRole("button", {
      name: "Continuar con cuadras",
    });
    expect(post).not.toHaveBeenCalled();
    const table = screen.getByRole("table", {
      name: /Distribución de Puertas/,
    });
    expect(
      within(table).getByRole("row", { name: /Resueltos/ }),
    ).toHaveTextContent("25 %");
    expect(
      within(table).getByRole("row", { name: /Por revisar/ }),
    ).toHaveTextContent("50 %");
    expect(
      screen.getByText(/2 ubicaciones esperan revisión/),
    ).toBeInTheDocument();
    await user.click(advance);
    await waitFor(() =>
      expect(post).toHaveBeenCalledWith(`/runs/${run.id}/advance`, {
        stage: "block",
      }),
    );
  });
  it("keeps quality and stage filters in result reads, review links and exports", async () => {
    const user = setup(<QualityPanel run={run} />);
    await user.selectOptions(
      await screen.findByLabelText("Flag de calidad del filtro"),
      "1",
    );
    await user.selectOptions(
      screen.getByLabelText("Estado de revisión del filtro"),
      "quick_review",
    );
    await user.selectOptions(screen.getByLabelText("Etapa del filtro"), "door");
    expect(
      screen.getByRole("link", { name: "Abrir revisión rápida" }),
    ).toHaveAttribute(
      "href",
      expect.stringContaining(
        "quality_flag=1&quality_stage=door&review_state=quick_review",
      ),
    );
    await waitFor(() =>
      expect(request).toHaveBeenCalledWith(
        expect.stringContaining(
          "quality_flag=1&quality_stage=door&review_state=quick_review",
        ),
      ),
    );
    await user.click(
      screen.getByRole("button", { name: "Preparar exportación" }),
    );
    await waitFor(() =>
      expect(post).toHaveBeenCalledWith(
        `/runs/${run.id}/exports`,
        expect.objectContaining({
          quality_flag: 1,
          review_state: "quick_review",
          quality_stage: "door",
          format: "xlsx",
        }),
      ),
    );
  });
  it("does not offer stage advancement to an analyst or while processing", async () => {
    auth.user.role = "analyst";
    setup(<QualityPanel run={{ ...run, status: "PROCESSING" }} />);
    await screen.findByLabelText("Flag de calidad del filtro");
    expect(
      screen.queryByRole("button", { name: "Continuar con cuadras" }),
    ).not.toBeInTheDocument();
  });
  it("does not retrofit quality labels on legacy runs", () => {
    setup(<QualityPanel run={{ ...run, config: {} }} />);
    expect(
      screen.getByText("Flags no evaluados en esta ejecución"),
    ).toBeInTheDocument();
    expect(request).not.toHaveBeenCalled();
  });
  it("retains quality filters when moving to the next review case", () => {
    const filters = readReviewFilters(
      new URLSearchParams(
        "run_id=r&quality_flag=1&quality_stage=door&review_state=quick_review",
      ),
    );
    expect(reviewParams(filters).get("quality_flag")).toBe("1");
    const next = nextReviewParams(
      `/review?${reviewParams(filters)}`,
      "r",
      "old-case",
    );
    expect(next.get("quality_stage")).toBe("door");
    expect(next.get("quality_flag")).toBe("1");
    expect(next.get("exclude_id")).toBe("old-case");
    expect(next.get("review_state")).toBe("quick_review");
  });
});
describe("five independent Excel references", () => {
  it("imports a staged door source without assuming its CRS and uses a separate upload resume slot", async () => {
    const onSelect = vi.fn();
    vi.mocked(uploadFile).mockResolvedValue({
      id: "door-upload",
      filename: "doors.xlsx",
      size: 10,
      offset: 10,
      status: "COMPLETE",
    });
    vi.mocked(post).mockImplementation(async (path) =>
      path.endsWith("/preview")
        ? {
            kind: "doors",
            columns: ["UBIGEO", "NOMVIA", "P17"],
            sheets: ["Puertas"],
            sheet: "Puertas",
            suggested_mapping: {
              ubigeo: "UBIGEO",
              street_name: "NOMVIA",
              door_number: "P17",
            },
            warnings: [],
          }
        : {
            id: "new-reference",
            name: "doors",
            version: "v1",
            source: "Pre Censos",
            feature_count: 0,
            config: {
              reference_excel: {
                kind: "doors",
                ready_rows: 0,
                staged_rows: 1,
                readiness: "staged",
              },
            },
          },
    );
    const user = setup(
      <ReferenceExcelCards
        catalogs={[]}
        selected={{}}
        onSelect={onSelect}
        onBusy={vi.fn()}
      />,
    );
    expect(screen.getAllByRole("article")).toHaveLength(5);
    const card = screen.getAllByRole("article")[0];
    await user.click(
      within(card).getByText("Importar Excel de puertas / viviendas"),
    );
    await user.upload(
      within(card).getByLabelText("Archivo Excel · Puertas / viviendas"),
      new File(["synthetic"], "doors.xlsx", {
        type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
      }),
    );
    fireEvent.submit(card.querySelector("form")!);
    await user.type(
      await within(card).findByLabelText("Versión de la fuente"),
      "v1",
    );
    expect(
      within(card).getByLabelText(
        "Sistema de coordenadas · Puertas / viviendas",
      ),
    ).toHaveValue("");
    await user.click(
      within(card).getByRole("button", {
        name: "Guardar y utilizar referencia",
      }),
    );
    await waitFor(() =>
      expect(onSelect).toHaveBeenCalledWith("doors", "new-reference"),
    );
    expect(uploadFile).toHaveBeenCalledWith(
      expect.any(File),
      "quality-user",
      expect.any(Function),
      undefined,
      "reference.doors",
    );
    expect(post).toHaveBeenCalledWith(
      "/reference-excels",
      expect.objectContaining({
        kind: "doors",
        crs: null,
        crs_evidence: null,
        mapping: {
          ubigeo: "UBIGEO",
          street_name: "NOMVIA",
          door_number: "P17",
        },
      }),
    );
  });
});
