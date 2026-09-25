import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, useLocation, useNavigationType } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { Procedures } from "../pages/Procedures";
import { Statistics } from "../pages/Statistics";
import { post, request } from "../lib/api";
import type { Page, Run } from "../types";

vi.mock("../lib/api", () => ({ request: vi.fn(), post: vi.fn() }));
vi.mock("../auth", () => ({ useAuth: () => ({ user: { role: "admin" } }) }));
vi.mock("../components/RunActivity", () => ({
  RunActivity: ({ run }: { run: Run }) => (
    <div data-testid="selected-detail">{run.id}</div>
  ),
}));
vi.mock("../components/ResultsTable", () => ({
  ResultsTable: ({ runId }: { runId: string }) => (
    <div data-testid="selected-detail">{runId}</div>
  ),
}));

const fixture = (id: string, created: string): Run => ({
  id,
  created_at: created,
  name: `Lote ${id}`,
  filename: `${id}.xlsx`,
  status: "COMPLETED",
  source_rows: 6,
  location_units: 5,
  processed_units: 5,
  issue_rows: 0,
  rules_version: "synthetic",
  config: {},
  counts: {},
});
const old = fixture("historical", "2026-09-23T12:00:00Z");
const latest = fixture("latest", "2026-09-25T12:00:00Z");
const newer = fixture("newer", "2026-09-25T13:00:00Z");
const choices = [old, latest, newer];
let listed: Run[];
let listError: Error | null;
let deferred: Promise<Page<Run>> | undefined;
const pageOf = (items: Run[], pageSize = 100): Page<Run> => ({
  items,
  total: items.length,
  page: 1,
  page_size: pageSize,
});
const modules = [
  {
    name: "Procedimientos",
    Component: Procedures,
    path: "/procedures",
    query: "view=history",
    key: "procedure-runs",
  },
  {
    name: "Estadística",
    Component: Statistics,
    path: "/statistics",
    query: "tab=records",
    key: "statistics-runs",
  },
];

function RouteProbe() {
  const location = useLocation();
  const navigation = useNavigationType();
  return (
    <output data-testid="route" data-navigation={navigation}>
      {location.pathname}
      {location.search}
    </output>
  );
}
function setup(
  module: (typeof modules)[number],
  search = module.query,
  cached?: Run[],
) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0, staleTime: 10_000 } },
  });
  if (cached)
    client.setQueryData([module.key], {
      pages: [pageOf(cached)],
      pageParams: [1],
    });
  render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[`${module.path}?${search}`]}>
        <module.Component />
        <RouteProbe />
      </MemoryRouter>
    </QueryClientProvider>,
  );
  return { client, user: userEvent.setup() };
}
function selector() {
  return screen.getByRole("combobox", { name: /^Procesamiento a consultar/ });
}
function routeParams() {
  return new URL(screen.getByTestId("route").textContent!, "http://local")
    .searchParams;
}

beforeEach(() => {
  vi.clearAllMocks();
  listed = [latest, old];
  listError = null;
  deferred = undefined;
  vi.mocked(request).mockImplementation(async (path) => {
    if (path.startsWith("/runs?")) {
      if (listError) throw listError;
      return deferred ?? pageOf(listed);
    }
    if (path.includes("/statistics?"))
      return {
        generated_at: latest.created_at,
        totals: {
          units: 5,
          source_rows: 6,
          accepted: 0,
          mapped: 0,
          excluded: 0,
        },
        resolutions: [{ resolution: "SIN_COINCIDENCIA", units: 5 }],
        flags: [],
        review_states: [],
        districts: [],
        map: { features: [], layers: {}, total: 0, shown: 0, truncated: false },
      };
    const run = choices.find((item) => path === `/runs/${item.id}`);
    if (run) return run;
    throw new Error(`Unexpected synthetic request: ${path}`);
  });
});

describe.each(modules)("default selection in $name", (module) => {
  it("opens the server's latest run and replaces the URL without executing an operation", async () => {
    setup(module);
    await waitFor(() => expect(selector()).toHaveValue(latest.id));
    expect(await screen.findByTestId("selected-detail")).toHaveTextContent(
      latest.id,
    );
    expect(routeParams().get("run_id")).toBe(latest.id);
    expect(routeParams().get(module.query.split("=")[0])).toBe(
      module.query.split("=")[1],
    );
    expect(screen.getByTestId("route")).toHaveAttribute(
      "data-navigation",
      "REPLACE",
    );
    expect(post).not.toHaveBeenCalled();
  });

  it("keeps an explicit historical run even when it is absent from the first list page", async () => {
    listed = [latest];
    setup(module, `${module.query}&run_id=${old.id}`);
    expect(await screen.findByTestId("selected-detail")).toHaveTextContent(
      old.id,
    );
    expect(selector()).toHaveValue(old.id);
    expect(routeParams().get("run_id")).toBe(old.id);
    expect(request).not.toHaveBeenCalledWith(`/runs/${latest.id}`);
    expect(post).not.toHaveBeenCalled();
  });

  it("keeps a manual historical or blank selection after the list refreshes", async () => {
    const { client, user } = setup(module);
    await waitFor(() => expect(selector()).toHaveValue(latest.id));
    await user.selectOptions(selector(), old.id);
    listed = [newer, latest, old];
    await act(async () => {
      await client.invalidateQueries({ queryKey: [module.key] });
    });
    expect(selector()).toHaveValue(old.id);
    expect(routeParams().get("run_id")).toBe(old.id);
    await user.selectOptions(selector(), "");
    await act(async () => {
      await client.invalidateQueries({ queryKey: [module.key] });
    });
    expect(selector()).toHaveValue("");
    expect(routeParams().has("run_id")).toBe(true);
    expect(routeParams().get("run_id")).toBe("");
    expect(post).not.toHaveBeenCalled();
  });

  it("waits for the server before choosing instead of using a stale cached list", async () => {
    let resolveList!: (value: Page<Run>) => void;
    deferred = new Promise((resolve) => {
      resolveList = resolve;
    });
    setup(module, module.query, [old]);
    expect(screen.getByText("Consultando procesamientos…")).toBeVisible();
    expect(selector()).toHaveValue("");
    expect(routeParams().has("run_id")).toBe(false);
    expect(request).not.toHaveBeenCalledWith(`/runs/${old.id}`);
    await act(async () => {
      resolveList(pageOf([latest, old]));
    });
    await waitFor(() => expect(selector()).toHaveValue(latest.id));
    expect(await screen.findByTestId("selected-detail")).toHaveTextContent(
      latest.id,
    );
  });

  it("shows a real empty state without selecting or starting anything", async () => {
    listed = [];
    setup(module);
    expect(
      await screen.findByRole("heading", { name: "Aún no hay procesamientos" }),
    ).toBeVisible();
    expect(selector()).toHaveValue("");
    expect(routeParams().has("run_id")).toBe(false);
    expect(request).not.toHaveBeenCalledWith(`/runs/${latest.id}`);
    expect(post).not.toHaveBeenCalled();
  });

  it("reports a list error and selects only after a successful explicit retry", async () => {
    listError = new Error("No se pudo consultar la lista sintética");
    const { user } = setup(module);
    expect(await screen.findByRole("alert")).toHaveTextContent(
      listError.message,
    );
    expect(routeParams().has("run_id")).toBe(false);
    expect(
      screen.queryByRole("heading", { name: "Aún no hay procesamientos" }),
    ).not.toBeInTheDocument();
    listError = null;
    await user.click(screen.getByRole("button", { name: "Volver a intentar" }));
    await waitFor(() => expect(selector()).toHaveValue(latest.id));
    expect(await screen.findByTestId("selected-detail")).toHaveTextContent(
      latest.id,
    );
    expect(post).not.toHaveBeenCalled();
  });
});
