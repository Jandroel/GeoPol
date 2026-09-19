import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ResultDetail } from "../pages/ResultDetail";
import type { LocationResult } from "../types";

vi.mock("../auth", () => ({
  useAuth: () => ({
    user: { id: "reviewer-1", username: "test-reviewer", role: "reviewer" },
  }),
}));
vi.mock("../components/LocationMap", () => ({
  default: () => <div>Visor local</div>,
}));
const result: LocationResult = {
  id: "loc-1",
  run_id: "run-1",
  complaint_id: "SYNTHETIC-1",
  location_original: "Av. Prueba 120",
  location_normalized: "AVENIDA PRUEBA 120",
  ubigeo: "150101",
  resolution: "REVISION_REQUERIDA",
  method: "EXACT",
  precision: "PUERTA",
  evidence_band: "REVISION",
  product: "NINGUNO",
  latitude: null,
  longitude: null,
  reason: "Territorio por corroborar",
  revision: 3,
  manual: false,
  candidates: [
    {
      id: "candidate-1",
      label: "Puerta de prueba",
      method: "EXACT",
      precision: "PUERTA",
      latitude: -12,
      longitude: -77,
      score: 100,
      evidence: ["Coincidencia exacta"],
    },
  ],
  history: [],
};
function setup() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={["/results/loc-1"]}>
        <Routes>
          <Route path="/results/:id" element={<ResultDetail />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}
describe("review workflow", () => {
  beforeEach(() => {
    vi.unstubAllGlobals();
  });
  it("retains candidates after claim and sends the selected candidate with the current revision", async () => {
    const calls: Record<string, unknown>[] = [];
    let claimed = false;
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string, options: RequestInit = {}) => {
        if (url.endsWith("/claim")) {
          claimed = true;
          return Response.json({
            ...result,
            candidates: undefined,
            review_owner: "reviewer-1",
            review_expires_at: new Date(Date.now() + 600000).toISOString(),
          });
        }
        if (url.endsWith("/decisions")) {
          calls.push(JSON.parse(options.body as string));
          return Response.json({
            ...result,
            revision: 4,
            resolution: "ACEPTADO_MANUAL",
          });
        }
        return Response.json({
          ...result,
          ...(claimed
            ? {
                review_owner: "reviewer-1",
                review_expires_at: new Date(Date.now() + 600000).toISOString(),
              }
            : {}),
        });
      }),
    );
    setup();
    const user = userEvent.setup();
    await user.click(
      await screen.findByRole("button", { name: "Tomar revisión" }),
    );
    await user.selectOptions(
      await screen.findByLabelText("Candidato"),
      "candidate-1",
    );
    await user.type(
      screen.getByLabelText("Motivo de la decisión"),
      "Verificado en catálogo sintético documentado",
    );
    await user.click(
      screen.getByRole("button", { name: "Registrar decisión" }),
    );
    await waitFor(() => expect(calls).toHaveLength(1));
    expect(calls[0]).toMatchObject({
      expected_revision: 3,
      action: "accept_candidate",
      candidate_id: "candidate-1",
      reason: "Verificado en catálogo sintético documentado",
    });
    expect(await screen.findByText(/Decisión registrada/)).toBeInTheDocument();
  });
  it("surfaces a concurrent edit conflict and refreshes the stale result", async () => {
    let reads = 0;
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string) => {
        if (url.endsWith("/decisions"))
          return Response.json(
            { detail: "La revisión cambió; vuelva a tomar el registro" },
            { status: 409 },
          );
        reads++;
        return Response.json({
          ...result,
          review_owner: "reviewer-1",
          review_expires_at: new Date(Date.now() + 600000).toISOString(),
        });
      }),
    );
    setup();
    const user = userEvent.setup();
    await user.selectOptions(
      await screen.findByLabelText("Acción"),
      "unresolved",
    );
    await user.type(
      screen.getByLabelText("Motivo de la decisión"),
      "Evidencia insuficiente para ubicar",
    );
    await user.click(
      screen.getByRole("button", { name: "Registrar decisión" }),
    );
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "La revisión cambió",
    );
    await waitFor(() => expect(reads).toBeGreaterThan(1));
  });
});
