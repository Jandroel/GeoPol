import { act, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ResultsTable } from "../components/ResultsTable";
import { request } from "../lib/api";
import type { LocationResult, Page } from "../types";

vi.mock("../lib/api", () => ({ request: vi.fn() }));

function response(total: number, page = 1): Page<LocationResult> {
  const start = (page - 1) * 25;
  const count = Math.min(25, Math.max(0, total - start));
  return {
    total,
    page,
    page_size: 25,
    items: Array.from(
      { length: count },
      (_, offset) =>
        ({
          id: `synthetic-location-${start + offset + 1}`,
          complaint_id: `SYN-${start + offset + 1}`,
          run_id: "synthetic-run",
          location_original: "CALLE DE PRUEBA 123",
          location_normalized: "CALLE DE PRUEBA 123",
          ubigeo: "150101",
          resolution: "REVISION_REQUERIDA",
          quality_flag: 1,
          quality_stage: "door",
          review_state: "quick_review",
          precision: "PUERTA",
          product: "PUNTO",
        }) as LocationResult,
    ),
  };
}
function setup(element = <ResultsTable runId="synthetic-run" />) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 } },
  });
  const wrapper = ({ children }: { children: React.ReactNode }) => (
    <QueryClientProvider client={client}>
      <MemoryRouter>{children}</MemoryRouter>
    </QueryClientProvider>
  );
  return { ...render(element, { wrapper }), client, user: userEvent.setup() };
}
const totalBlock = () =>
  screen.getByRole("status", { name: "Total de resultados" });

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(request).mockImplementation(async (path) => {
    const params = new URL(path, "http://localhost").searchParams;
    return response(1351, Number(params.get("page")));
  });
});

describe("visible result totals", () => {
  it("shows the API total beside filters and the actual range across pages, not the number of rows loaded", async () => {
    const { user } = setup();
    await waitFor(() => expect(totalBlock()).toHaveTextContent("1,351"));
    expect(totalBlock()).toHaveTextContent("Total de ubicaciones");
    expect(totalBlock()).toHaveTextContent("Mostrando 1–25 de 1,351");
    expect(screen.getAllByRole("row")).toHaveLength(26);
    await user.click(screen.getByRole("button", { name: "Página siguiente" }));
    await waitFor(() =>
      expect(totalBlock()).toHaveTextContent("Mostrando 26–50 de 1,351"),
    );
    expect(
      vi
        .mocked(request)
        .mock.calls.every(([path]) =>
          path.startsWith("/runs/synthetic-run/results?"),
        ),
    ).toBe(true);
  });
  it("uses submitted search and resolution totals and resets to the first page without counting draft text", async () => {
    vi.mocked(request).mockImplementation(async (path) => {
      const params = new URL(path, "http://localhost").searchParams;
      const total = params.get("resolution") ? 2 : params.get("q") ? 31 : 1351;
      return response(total, Number(params.get("page")));
    });
    const { user } = setup();
    await waitFor(() => expect(totalBlock()).toHaveTextContent("1,351"));
    await user.click(screen.getByRole("button", { name: "Página siguiente" }));
    await waitFor(() =>
      expect(totalBlock()).toHaveTextContent("Mostrando 26–50"),
    );
    await user.type(
      screen.getByRole("textbox", { name: "Buscar denuncia o dirección" }),
      "PRUEBA",
    );
    expect(totalBlock()).toHaveTextContent("Total de ubicaciones");
    expect(totalBlock()).toHaveTextContent("1,351");
    await user.click(screen.getByRole("button", { name: /^Buscar$/ }));
    await waitFor(() =>
      expect(totalBlock()).toHaveTextContent("Mostrando 1–25 de 31"),
    );
    expect(totalBlock()).toHaveTextContent("Ubicaciones en este filtro");
    await user.click(screen.getByRole("button", { name: "Página siguiente" }));
    await waitFor(() =>
      expect(totalBlock()).toHaveTextContent("Mostrando 26–31 de 31"),
    );
    await user.selectOptions(
      screen.getByRole("combobox", { name: "Resolución" }),
      "ACEPTADO_AUTOMATICO",
    );
    await waitFor(() =>
      expect(totalBlock()).toHaveTextContent("Mostrando 1–2 de 2"),
    );
    expect(
      vi
        .mocked(request)
        .mock.calls.some(
          ([path]) =>
            path.includes("page=2") &&
            path.includes("resolution=ACEPTADO_AUTOMATICO"),
        ),
    ).toBe(false);
  });
  it("resets external quality filters and preserves the review endpoint scope", async () => {
    vi.mocked(request).mockImplementation(async (path) => {
      const params = new URL(path, "http://localhost").searchParams;
      return response(
        params.get("quality_flag") ? 3 : 40,
        Number(params.get("page")),
      );
    });
    const { user, rerender } = setup(<ResultsTable review />);
    await waitFor(() =>
      expect(totalBlock()).toHaveTextContent("Mostrando 1–25 de 40"),
    );
    expect(totalBlock()).toHaveTextContent("Ubicaciones en esta bandeja");
    await user.click(screen.getByRole("button", { name: "Página siguiente" }));
    await waitFor(() =>
      expect(totalBlock()).toHaveTextContent("Mostrando 26–40 de 40"),
    );
    rerender(
      <ResultsTable
        review
        qualityFlag={1}
        qualityStage="door"
        reviewState="quick_review"
      />,
    );
    await waitFor(() =>
      expect(totalBlock()).toHaveTextContent("Mostrando 1–3 de 3"),
    );
    expect(totalBlock()).toHaveTextContent("Ubicaciones en este filtro");
    expect(
      vi
        .mocked(request)
        .mock.calls.some(
          ([path]) =>
            path.includes("quality_flag=1") && path.includes("page=2"),
        ),
    ).toBe(false);
    expect(vi.mocked(request).mock.calls.at(-1)?.[0]).toContain(
      "/review?page=1",
    );
    expect(vi.mocked(request).mock.calls.at(-1)?.[0]).toContain(
      "quality_flag=1&quality_stage=door&review_state=quick_review",
    );
    rerender(<ResultsTable review />);
    await waitFor(() =>
      expect(totalBlock()).toHaveTextContent("Mostrando 1–25 de 40"),
    );
  });
  it("does not show zero while loading or after an error, and reports a real empty filter as zero", async () => {
    let finish!: (value: Page<LocationResult>) => void;
    vi.mocked(request).mockImplementation(
      () =>
        new Promise((resolve) => {
          finish = resolve;
        }),
    );
    const { client } = setup(
      <ResultsTable runId="synthetic-run" qualityFlag={2} />,
    );
    expect(totalBlock()).toHaveTextContent("Consultando total…");
    expect(
      within(totalBlock()).queryByText("0", { exact: true }),
    ).not.toBeInTheDocument();
    await act(async () => finish(response(0)));
    await waitFor(() =>
      expect(
        within(totalBlock()).getByText("0", { exact: true }),
      ).toBeInTheDocument(),
    );
    expect(totalBlock()).toHaveTextContent("Sin ubicaciones para mostrar");
    vi.mocked(request).mockRejectedValue(
      new Error("No se pudo cargar el total"),
    );
    await act(async () => {
      await client.invalidateQueries({ queryKey: ["results"] });
    });
    await waitFor(() =>
      expect(totalBlock()).toHaveTextContent("Total no disponible"),
    );
    expect(
      within(totalBlock()).queryByText("0", { exact: true }),
    ).not.toBeInTheDocument();
  });
  it("recovers a valid page when a live update removes the current last page", async () => {
    let currentTotal = 26;
    vi.mocked(request).mockImplementation(async (path) =>
      response(
        currentTotal,
        Number(new URL(path, "http://localhost").searchParams.get("page")),
      ),
    );
    const { user, client } = setup();
    await waitFor(() =>
      expect(totalBlock()).toHaveTextContent("Mostrando 1–25 de 26"),
    );
    await user.click(screen.getByRole("button", { name: "Página siguiente" }));
    await waitFor(() =>
      expect(totalBlock()).toHaveTextContent("Mostrando 26–26 de 26"),
    );
    currentTotal = 4;
    await act(async () => {
      await client.invalidateQueries({ queryKey: ["results"] });
    });
    await waitFor(() =>
      expect(totalBlock()).toHaveTextContent("Mostrando 1–4 de 4"),
    );
    expect(
      screen.getByRole("button", { name: "Página anterior" }),
    ).toBeDisabled();
    expect(screen.getByText(/Página 1 de 1/)).toBeInTheDocument();
  });
});
