import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { Statistics, type StatisticsData } from "../pages/Statistics";
import { request } from "../lib/api";
import type { Run } from "../types";
import type { StatisticsFeature } from "../components/StatisticsMap";

vi.mock("../lib/api", () => ({ request: vi.fn() }));
vi.mock("../components/ExportPanel", () => ({
  ExportPanel: ({ runId }: { runId: string }) => <div>Exportar {runId}</div>,
}));
vi.mock("../components/ResultsTable", () => ({
  ResultsTable: ({ runId }: { runId: string }) => (
    <div>Registros de {runId}</div>
  ),
}));
vi.mock("../components/StatisticsMap", () => ({
  statisticLayers: {
    original: { label: "Coordenadas de origen", color: "green" },
    reference: { label: "Referencia geográfica", color: "blue" },
    manual: { label: "Revisión manual", color: "orange" },
    other: { label: "Otro método validado", color: "purple" },
  },
  StatisticsMap: ({ features }: { features: StatisticsFeature[] }) => (
    <div data-testid="statistics-map">
      {features.length} geometrías visibles
    </div>
  ),
}));
const run: Run = {
  id: "statistics-run",
  name: "Lote sintético",
  filename: "sintetico.xlsx",
  status: "COMPLETED",
  created_at: "2026-09-25T12:00:00Z",
  source_rows: 5,
  location_units: 3,
  processed_units: 3,
  issue_rows: 0,
  rules_version: "test",
  config: {},
  counts: {},
};
const stats: StatisticsData = {
  run_id: run.id,
  generated_at: "2026-09-25T12:05:00Z",
  totals: {
    units: 3,
    source_rows: 5,
    accepted: 2,
    mapped: 2,
    without_accepted_geometry: 1,
    excluded: 1,
    issue_rows: 0,
  },
  resolutions: [
    { resolution: "ACEPTADO_AUTOMATICO", units: 1 },
    { resolution: "ACEPTADO_MANUAL", units: 1 },
    { resolution: "EXCLUIDO_FLAG_10", units: 1 },
  ],
  flags: [
    { flag: 1, units: 2 },
    { flag: 10, units: 1 },
  ],
  review_states: [
    { state: "automatic", units: 1 },
    { state: "accepted_manual", units: 1 },
    { state: "excluded", units: 1 },
  ],
  districts: [
    {
      ubigeo: "150101",
      district: "Distrito sintético",
      name_conflict: false,
      units: 3,
      source_rows: 5,
      mapped: 2,
    },
  ],
  map: {
    total: 2,
    shown: 2,
    limit: 2000,
    truncated: false,
    layers: { original: 1, manual: 1 },
    features: ["original", "manual"].map((layer, index) => ({
      type: "Feature",
      id: `synthetic-${index}`,
      geometry: { type: "Point", coordinates: [-77, -12] },
      properties: {
        id: `synthetic-${index}`,
        layer: layer as "original" | "manual",
        method: "COORD_ORIGINAL",
        ubigeo: "150101",
        precision: "COORDENADA",
      },
    })),
  },
};

function setup(path = `/statistics?run_id=${run.id}`) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 } },
  });
  render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[path]}>
        <Statistics />
      </MemoryRouter>
    </QueryClientProvider>,
  );
  return userEvent.setup();
}
beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(request).mockImplementation(async (path) =>
    path.includes("/statistics?")
      ? stats
      : path.startsWith("/runs?")
        ? { items: [run], total: 1, page: 1, page_size: 100 }
        : run,
  );
});

describe("statistics module", () => {
  it("shows selected-run aggregates and excludes flag10 from pending states", async () => {
    setup();
    await screen.findByRole("heading", { name: "Resumen de resolución" });
    expect(
      screen.getByText("Con geometría aceptada").parentElement,
    ).toHaveTextContent("2");
    expect(
      screen.getByText("Excluidas · flag 10").parentElement,
    ).toHaveTextContent("1");
    expect(
      screen.getByText("No hay ubicaciones pendientes en este procesamiento."),
    ).toBeVisible();
    expect(screen.queryByText("Evolución trimestral")).not.toBeInTheDocument();
    expect(
      screen.getByText(
        /Resultados vigentes dentro del procesamiento seleccionado/,
      ),
    ).toBeVisible();
  });

  it("layer selection filters only map geometry and does not change aggregates", async () => {
    const user = setup();
    expect(await screen.findByTestId("statistics-map")).toHaveTextContent(
      "2 geometrías visibles",
    );
    await user.click(
      screen.getByRole("checkbox", { name: /Coordenadas de origen/ }),
    );
    expect(screen.getByTestId("statistics-map")).toHaveTextContent(
      "1 geometrías visibles",
    );
    expect(
      screen.getByText("Con geometría aceptada").parentElement,
    ).toHaveTextContent("2");
    await user.selectOptions(
      screen.getByLabelText("Máximo de geometrías"),
      "5000",
    );
    await waitFor(() =>
      expect(request).toHaveBeenCalledWith(
        `/runs/${run.id}/statistics?map_limit=5000`,
      ),
    );
  });

  it("keeps record and export tabs scoped to the selected run", async () => {
    const user = setup();
    await screen.findByRole("heading", { name: "Resumen de resolución" });
    await user.click(screen.getByRole("tab", { name: "Detalle de registros" }));
    expect(screen.getByText(`Registros de ${run.id}`)).toBeVisible();
    await user.click(screen.getByRole("tab", { name: "Descargas" }));
    expect(screen.getByText(`Exportar ${run.id}`)).toBeVisible();
  });

  it("does not generate an export while the selected run is active", async () => {
    vi.mocked(request).mockImplementation(async (path) =>
      path.startsWith("/runs?")
        ? { items: [run], total: 1, page: 1, page_size: 100 }
        : { ...run, status: "PROCESSING" },
    );
    setup(`/statistics?run_id=${run.id}&tab=exports`);
    expect(
      await screen.findByRole("heading", {
        name: "La descarga se habilita al finalizar",
      }),
    ).toBeVisible();
    expect(screen.queryByText(`Exportar ${run.id}`)).not.toBeInTheDocument();
  });
});
