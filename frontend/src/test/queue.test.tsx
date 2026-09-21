import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { Review } from "../pages/Review";
import { ReprocessPanel } from "../components/ReprocessPanel";
import {
  nextReviewParams,
  readReviewFilters,
  reservationIsLive,
  validReviewReturn,
} from "../lib/review";
import type { Run } from "../types";

vi.mock("../auth", () => ({
  useAuth: () => ({ user: { id: "synthetic-admin", role: "admin" } }),
}));
const run: Run = {
  id: "run-1",
  name: "Ejecución sintética",
  status: "COMPLETED",
  filename: "synthetic.csv",
  created_at: "2026-01-01T00:00:00Z",
  source_rows: 3,
  location_units: 3,
  processed_units: 3,
  issue_rows: 0,
  rules_version: "2026.1",
  counts: {},
  config: {},
};
function Path() {
  const location = useLocation();
  return <div data-testid="path">{location.pathname + location.search}</div>;
}
function setup(path: string, element: React.ReactNode) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[path]}>
        <Path />
        <Routes>
          <Route path="/review" element={element} />
          <Route path="/runs/:id" element={element} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}
afterEach(() => vi.unstubAllGlobals());
describe("review queue scope", () => {
  it("defaults to actionable work while showing reference blockers and preserves filters in detail links", async () => {
    const reads: string[] = [];
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string) => {
        reads.push(url);
        if (url.includes("/summary"))
          return Response.json({
            open: {
              actionable: 1,
              needs_reference: 9,
              needs_data: 2,
              technical: 0,
            },
            closed: 5,
            total: 17,
          });
        if (url.includes("/runs"))
          return Response.json({
            items: [run],
            total: 1,
            page: 1,
            page_size: 100,
          });
        return Response.json({
          items: [
            {
              id: "loc-1",
              run_id: "run-1",
              complaint_id: "SYNTHETIC-1",
              location_original: "Av. Prueba",
              location_normalized: "AVENIDA PRUEBA",
              ubigeo: "150101",
              resolution: "REVISION_REQUERIDA",
              reason: "MULTIPLES_CANDIDATOS",
              candidate_count: 2,
              review_status: "OPEN",
              review_bucket: "actionable",
            },
          ],
          total: 1,
          page: 1,
          page_size: 25,
        });
      }),
    );
    setup("/review?run_id=run-1&q=SYNTHETIC", <Review />);
    const actionable = await screen.findByRole("button", {
      name: /Revisión accionable/,
    });
    await waitFor(() => expect(actionable).toHaveTextContent("1"));
    expect(actionable).toHaveAttribute("aria-pressed", "true");
    expect(
      screen.getByRole("button", { name: /Referencia pendiente/ }),
    ).toHaveTextContent("9");
    const detail = await screen.findByRole("link", { name: "Examinar" });
    expect(decodeURIComponent(detail.getAttribute("href")!)).toContain(
      "run_id=run-1",
    );
    expect(decodeURIComponent(detail.getAttribute("href")!)).toContain(
      "bucket=actionable",
    );
    expect(
      screen.getByText(
        "Hay más de un candidato compatible; compara la evidencia.",
      ),
    ).toBeInTheDocument();
    await userEvent
      .setup()
      .click(screen.getByRole("button", { name: /Finalizados: 5/ }));
    await waitFor(() =>
      expect(screen.getByLabelText("Etapa")).toHaveValue("closed"),
    );
    expect(screen.getByLabelText("Motivo de atención")).toHaveValue("all");
    expect(
      screen.getByText(/Finalizados incluye resoluciones automáticas/),
    ).toBeInTheDocument();
    await waitFor(() =>
      expect(
        reads.some(
          (url) => url.includes("stage=closed") && url.includes("bucket=all"),
        ),
      ).toBe(true),
    );
    expect(
      reads
        .filter((url) => url.includes("/summary"))
        .every(
          (url) => url.includes("run_id=run-1") && url.includes("q=SYNTHETIC"),
        ),
    ).toBe(true);
  });
  it("validates return destinations and forces next selection to pending records", () => {
    expect(
      reservationIsLive(
        "2026-01-01T12:00:00",
        Date.parse("2026-01-01T12:00:01Z"),
      ),
    ).toBe(false);
    expect(
      reservationIsLive(
        "2026-01-01T12:00:00Z",
        Date.parse("2026-01-01T11:59:59Z"),
      ),
    ).toBe(true);
    expect(validReviewReturn("https://external.invalid/review", "run-1")).toBe(
      "/runs/run-1",
    );
    expect(
      readReviewFilters(new URLSearchParams("bucket=constructor&page=-1")),
    ).toMatchObject({ bucket: "actionable", page: 1 });
    expect(
      Object.fromEntries(
        nextReviewParams(
          "/review?run_id=run-1&stage=closed&bucket=all&include_superseded=true",
          "other",
          "loc-1",
        ),
      ),
    ).toMatchObject({
      run_id: "run-1",
      stage: "open",
      bucket: "all",
      include_superseded: "true",
      exclude_id: "loc-1",
    });
  });
});
describe("reference-aware reprocessing", () => {
  it.each(["ref-2", ""])(
    "creates a new execution with the explicitly selected reference %s",
    async (selected) => {
      const writes: unknown[] = [];
      vi.stubGlobal(
        "fetch",
        vi.fn(async (url: string, options: RequestInit = {}) => {
          if (url.endsWith("/reprocess")) {
            writes.push(JSON.parse(options.body as string));
            return Response.json({
              ...run,
              id: "run-2",
              parent_run_id: "run-1",
            });
          }
          return Response.json({
            items: [
              {
                id: "ref-2",
                name: "Catálogo sintético",
                version: "v2",
                source: "QA",
                feature_count: 2,
                sha256: "synthetic",
              },
            ],
            total: 1,
            page: 1,
            page_size: 100,
          });
        }),
      );
      setup(
        "/runs/run-1",
        <ReprocessPanel run={{ ...run, reference_id: "ref-1" }} />,
      );
      const select = await screen.findByLabelText(
        "Catálogo del nuevo procesamiento",
      );
      await waitFor(() => expect(select).toBeEnabled());
      await userEvent.setup().selectOptions(select, selected);
      await userEvent
        .setup()
        .click(
          screen.getByRole("button", { name: "Crear nuevo procesamiento" }),
        );
      await waitFor(() =>
        expect(screen.getByTestId("path")).toHaveTextContent("/runs/run-2"),
      );
      expect(writes).toEqual([{ reference_id: selected || null }]);
    },
  );
});
