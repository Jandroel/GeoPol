import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";
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
  review_status: "OPEN",
  review_bucket: "actionable",
  candidate_count: 1,
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
function CurrentPath() {
  const location = useLocation();
  return <div data-testid="path">{location.pathname + location.search}</div>;
}
function setup(initial = "/results/loc-1") {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[initial]}>
        <CurrentPath />
        <Routes>
          <Route path="/results/:id" element={<ResultDetail />} />
          <Route path="/review" element={<div>Bandeja</div>} />
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
    let saved = false;
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
          saved = true;
          claimed = false;
          calls.push(JSON.parse(options.body as string));
          return Response.json({
            ...result,
            revision: 4,
            resolution: "ACEPTADO_MANUAL",
            review_status: "CLOSED",
            review_bucket: "none",
          });
        }
        return Response.json({
          ...result,
          ...(saved
            ? {
                revision: 4,
                resolution: "ACEPTADO_MANUAL",
                review_status: "CLOSED",
                review_bucket: "none",
              }
            : {}),
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
      learn_address: false,
    });
    expect(await screen.findByText(/Decisión registrada/)).toBeInTheDocument();
  });
  it("surfaces a concurrent edit conflict and refreshes the stale result", async () => {
    let reads = 0;
    const nextRequests: string[] = [];
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string) => {
        if (url.includes("/review/next")) nextRequests.push(url);
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
      screen.getByRole("button", { name: "Guardar y siguiente" }),
    );
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "La revisión cambió",
    );
    await waitFor(() => expect(reads).toBeGreaterThan(1));
    expect(nextRequests).toEqual([]);
    expect(screen.getByLabelText("Motivo de la decisión")).toHaveValue(
      "Evidencia insuficiente para ubicar",
    );
    expect(screen.getByTestId("path")).toHaveTextContent("/results/loc-1");
  });
  it("saves before finding the next record, preserves filters and clears the whole decision form", async () => {
    const writes: { url: string; body: Record<string, unknown> }[] = [];
    let firstSaved = false;
    let secondClaimed = false;
    const requests: string[] = [];
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string, options: RequestInit = {}) => {
        requests.push(url);
        if (url.includes("/review/next")) {
          expect(firstSaved).toBe(true);
          return Response.json({ item: { ...result, id: "loc-2" } });
        }
        if (options.method === "POST") {
          writes.push({
            url,
            body: JSON.parse((options.body as string) || "{}"),
          });
          if (url.endsWith("/decisions")) firstSaved = true;
          if (url.includes("loc-2/claim")) secondClaimed = true;
        }
        const second = url.includes("loc-2");
        return Response.json({
          ...result,
          id: second ? "loc-2" : "loc-1",
          complaint_id: second ? "SYNTHETIC-2" : "SYNTHETIC-1",
          revision: second ? 8 : firstSaved ? 4 : 3,
          review_status: !second && firstSaved ? "CLOSED" : "OPEN",
          review_bucket: !second && firstSaved ? "none" : "actionable",
          ...((!second && !firstSaved) || (second && secondClaimed)
            ? {
                review_owner: "reviewer-1",
                review_expires_at: new Date(Date.now() + 600000).toISOString(),
              }
            : {}),
        });
      }),
    );
    const back =
      "/review?run_id=run-1&bucket=actionable&stage=open&q=SYNTHETIC&page=2";
    setup(`/results/loc-1?back=${encodeURIComponent(back)}`);
    const user = userEvent.setup();
    await user.selectOptions(
      await screen.findByLabelText("Acción"),
      "manual_point",
    );
    await user.click(
      screen.getByLabelText(
        "Reutilizar esta dirección validada en futuros lotes",
      ),
    );
    await user.type(screen.getByLabelText("Latitud"), "-12.3");
    await user.type(screen.getByLabelText("Longitud"), "-77.2");
    await user.type(
      screen.getByLabelText("Evidencia del punto"),
      "Fuente sintética de prueba documentada",
    );
    await user.type(
      screen.getByLabelText("Motivo de la decisión"),
      "Verificación sintética del primer punto",
    );
    await user.click(
      screen.getByRole("button", { name: "Guardar y siguiente" }),
    );
    expect(
      await screen.findByRole("heading", { name: "SYNTHETIC-2" }),
    ).toBeInTheDocument();
    expect(writes).toHaveLength(1);
    expect(writes[0].body).toMatchObject({
      action: "manual_point",
      expected_revision: 3,
      latitude: -12.3,
      longitude: -77.2,
      learn_address: true,
    });
    const next = new URL(
      requests.find((url) => url.includes("/review/next"))!,
      "http://local",
    );
    expect(Object.fromEntries(next.searchParams)).toMatchObject({
      run_id: "run-1",
      bucket: "actionable",
      stage: "open",
      q: "SYNTHETIC",
      exclude_id: "loc-1",
    });
    expect(screen.getByTestId("path").textContent).toContain(
      encodeURIComponent(back),
    );
    await user.click(screen.getByRole("button", { name: "Tomar revisión" }));
    expect(await screen.findByLabelText("Candidato")).toHaveValue("");
    expect(screen.getByLabelText("Motivo de la decisión")).toHaveValue("");
    await user.selectOptions(screen.getByLabelText("Acción"), "manual_point");
    expect(screen.getByLabelText("Latitud")).toHaveValue(null);
    expect(screen.getByLabelText("Longitud")).toHaveValue(null);
    expect(screen.getByLabelText("Evidencia del punto")).toHaveValue("");
    expect(screen.getByLabelText("Precisión espacial")).toHaveValue(
      "COORDENADA",
    );
    expect(
      screen.getByLabelText(
        "Reutilizar esta dirección validada en futuros lotes",
      ),
    ).not.toBeChecked();
  });
  it("allows explicit reuse of a candidate with a real area geometry and clears consent on action changes", async () => {
    const writes: Record<string, unknown>[] = [];
    const areaResult = {
      ...result,
      candidates: [
        {
          ...result.candidates![0],
          precision: "MANZANA",
          latitude: null,
          longitude: null,
          geometry: {
            type: "Polygon",
            coordinates: [
              [
                [-77, -12],
                [-77.01, -12],
                [-77.01, -12.01],
                [-77, -12],
              ],
            ],
          },
        },
      ],
      review_owner: "reviewer-1",
      review_expires_at: new Date(Date.now() + 600000).toISOString(),
    };
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string, options: RequestInit = {}) => {
        if (url.endsWith("/decisions"))
          writes.push(JSON.parse(options.body as string));
        return Response.json(areaResult);
      }),
    );
    setup();
    const user = userEvent.setup();
    await user.selectOptions(
      await screen.findByLabelText("Candidato"),
      "candidate-1",
    );
    expect(
      screen.getByText(/Área de referencia · No representa un punto exacto/),
    ).toBeInTheDocument();
    const consent = screen.getByLabelText(
      "Reutilizar esta dirección validada en futuros lotes",
    );
    expect(consent).not.toBeChecked();
    await user.click(consent);
    await user.selectOptions(screen.getByLabelText("Acción"), "unresolved");
    expect(
      screen.queryByLabelText(
        "Reutilizar esta dirección validada en futuros lotes",
      ),
    ).not.toBeInTheDocument();
    await user.selectOptions(
      screen.getByLabelText("Acción"),
      "accept_candidate",
    );
    expect(
      screen.getByLabelText(
        "Reutilizar esta dirección validada en futuros lotes",
      ),
    ).not.toBeChecked();
    await user.click(
      screen.getByLabelText(
        "Reutilizar esta dirección validada en futuros lotes",
      ),
    );
    await user.type(
      screen.getByLabelText("Motivo de la decisión"),
      "Área sintética verificada mediante polígono de referencia",
    );
    await user.click(
      screen.getByRole("button", { name: "Registrar decisión" }),
    );
    await waitFor(() => expect(writes).toHaveLength(1));
    expect(writes[0]).toMatchObject({
      action: "accept_candidate",
      candidate_id: "candidate-1",
      learn_address: true,
    });
  });
  it("releases the current reservation before explicitly returning to the filtered queue", async () => {
    const releases: string[] = [];
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string) => {
        if (url.endsWith("/release")) releases.push(url);
        return Response.json({
          ...result,
          review_owner: "reviewer-1",
          review_expires_at: new Date(Date.now() + 600000).toISOString(),
        });
      }),
    );
    const back = "/review?run_id=run-1&bucket=actionable&stage=open&page=3";
    setup(`/results/loc-1?back=${encodeURIComponent(back)}`);
    await userEvent
      .setup()
      .click(
        await screen.findByRole("button", { name: "Volver y liberar reserva" }),
      );
    await waitFor(() =>
      expect(screen.getByTestId("path").textContent).toBe(back),
    );
    expect(releases).toEqual(["/api/results/loc-1/release"]);
  });
  it("revokes a reused reference explicitly without taking a review reservation or changing a result", async () => {
    const calls: { url: string; body: Record<string, unknown> }[] = [];
    const memoryId = "synthetic-memory-id";
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string, options: RequestInit = {}) => {
        if (options.method === "POST") {
          calls.push({ url, body: JSON.parse(options.body as string) });
          return Response.json({ id: memoryId, active: false });
        }
        return Response.json({
          ...result,
          normalized: { learned_reference_id: memoryId },
          candidates: [
            {
              ...result.candidates![0],
              id: `memory:${memoryId}`,
              score: null,
              method: "DIRECCION_VALIDADA",
            },
          ],
        });
      }),
    );
    setup();
    const revoke = await screen.findByRole("button", {
      name: "Desactivar reutilización",
    });
    expect(
      screen.getAllByRole("button", { name: "Desactivar reutilización" }),
    ).toHaveLength(1);
    await userEvent.setup().click(revoke);
    expect(
      await screen.findByText("Reutilización desactivada"),
    ).toBeInTheDocument();
    expect(calls).toEqual([
      {
        url: `/api/address-memory/${memoryId}/revoke`,
        body: {
          reason: "Desactivación solicitada desde la ficha de ubicación",
        },
      },
    ]);
    expect(
      screen.queryByRole("button", { name: "Desactivar reutilización" }),
    ).not.toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Tomar revisión" }),
    ).toBeInTheDocument();
  });
});
