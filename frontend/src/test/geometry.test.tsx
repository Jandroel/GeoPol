import { render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import LocationMap from "../components/LocationMap";
import { canReuseCandidate, spatialPoint } from "../lib/geometry";
import type { Candidate, SpatialGeometry } from "../types";

const mapCalls = vi.hoisted(() => ({
  initialized: vi.fn(),
  source: vi.fn(),
  layer: vi.fn(),
  marker: vi.fn(),
  bounds: vi.fn(),
  remove: vi.fn(),
}));
vi.mock("maplibre-gl", () => ({
  setWorkerUrl: vi.fn(),
  Map: class {
    constructor() {
      mapCalls.initialized();
    }
    addControl() {}
    on(event: string, handler: () => void) {
      if (event === "load") handler();
    }
    addSource = mapCalls.source;
    addLayer = mapCalls.layer;
    fitBounds() {}
    remove = mapCalls.remove;
  },
  Marker: class {
    constructor() {
      mapCalls.marker();
    }
    setLngLat() {
      return this;
    }
    setPopup() {
      return this;
    }
    addTo() {
      return this;
    }
    getElement() {
      return document.createElement("div");
    }
  },
  Popup: class {
    setDOMContent() {
      return this;
    }
  },
  NavigationControl: class {},
  LngLatBounds: class {
    extend(position: unknown) {
      mapCalls.bounds(position);
      return this;
    }
  },
}));

const polygon: SpatialGeometry = {
  type: "Polygon",
  coordinates: [
    [
      [-77, -12],
      [-77.01, -12],
      [-77.01, -12.01],
      [-77, -12],
    ],
  ],
};
const line: SpatialGeometry = {
  type: "MultiLineString",
  coordinates: [
    [
      [-77, -12],
      [-77.01, -12.01],
    ],
    [
      [-77.02, -12],
      [-77.03, -12.01],
    ],
  ],
};
const candidate: Candidate = {
  id: "synthetic-area",
  label: "Tramo sintético",
  method: "VIA",
  precision: "VIA",
  latitude: null,
  longitude: null,
  score: 100,
  evidence: [],
  geometry: line,
};
beforeEach(() => vi.clearAllMocks());
afterEach(() => vi.unstubAllGlobals());
describe("real spatial geometry rendering", () => {
  it.each(["CRS_NO_CONFIRMADO", "COORDENADAS_CONTRADICTORIAS"])(
    "does not plot a declared coordinate with %s as WGS84",
    async (warning) => {
      const declared: Candidate = {
        id: "coord-original",
        label: "Original declarada",
        method: "COORD_ORIGINAL",
        precision: "COORDENADA",
        latitude: -12,
        longitude: -77,
        score: null,
        geometry: { type: "Point", coordinates: [-77, -12] },
        evidence: [warning],
      };
      const view = render(
        <LocationMap
          latitude={-12}
          longitude={-77}
          precision="COORDENADA"
          resultMethod="COORD_ORIGINAL"
          candidates={[declared]}
        />,
      );
      expect(
        screen.getByText(/se conservan en la ficha y no se dibujan/),
      ).toBeInTheDocument();
      await waitFor(() => expect(mapCalls.initialized).toHaveBeenCalled());
      view.unmount();
      expect(mapCalls.marker).not.toHaveBeenCalled();
    },
  );
  it("loads authenticated local context below results, retains their framing and attributes OSM", async () => {
    const fetch = vi.fn(async (_url: string) =>
      Response.json({
        type: "FeatureCollection",
        features: [
          {
            type: "Feature",
            id: "street-context",
            geometry: line,
            properties: {
              kind: "street",
              name: "Vía sintética",
              source: "OSM",
              version: "v1",
            },
          },
        ],
        truncated: true,
        reference_id: "reference-1",
        sources: ["OpenStreetMap"],
      }),
    );
    vi.stubGlobal("fetch", fetch);
    render(
      <LocationMap
        runId="run-1"
        ubigeo="150101"
        latitude={-12}
        longitude={-77}
        precision="PUERTA"
        candidates={[]}
      />,
    );
    await screen.findByText("Contexto local del catálogo · Cobertura parcial");
    await waitFor(() =>
      expect(mapCalls.source).toHaveBeenCalledWith(
        "local-context",
        expect.any(Object),
      ),
    );
    expect(fetch.mock.calls[0][0]).toBe(
      "/api/runs/run-1/map-context?ubigeo=150101",
    );
    expect(
      screen.getByRole("link", { name: "OpenStreetMap contributors" }),
    ).toBeInTheDocument();
    expect(mapCalls.bounds).not.toHaveBeenCalledWith([-77.03, -12.01]);
    expect(mapCalls.layer.mock.calls.map((call) => call[0].id)).toContain(
      "local-context-lines",
    );
  });
  it("renders result areas and candidate lines as GeoJSON layers, without creating centroid markers", async () => {
    const view = render(
      <LocationMap
        latitude={null}
        longitude={null}
        precision="MANZANA"
        geometry={polygon}
        candidates={[candidate]}
      />,
    );
    await waitFor(() => expect(mapCalls.source).toHaveBeenCalledOnce());
    const collection = mapCalls.source.mock.calls[0][1].data;
    expect(
      collection.features.map(
        (feature: { geometry: SpatialGeometry }) => feature.geometry,
      ),
    ).toEqual([line, polygon]);
    expect(mapCalls.layer.mock.calls.map((call) => call[0].type)).toEqual([
      "fill",
      "line",
    ]);
    expect(mapCalls.marker).not.toHaveBeenCalled();
    expect(mapCalls.bounds).toHaveBeenCalledWith([-77.03, -12.01]);
    expect(screen.getByLabelText("Leyenda del visor")).toBeInTheDocument();
    view.unmount();
    expect(mapCalls.remove).toHaveBeenCalledOnce();
  });
  it("does not turn an old area centroid into a point or a reusable address", () => {
    const centroid = {
      ...candidate,
      precision: "CUADRA",
      latitude: -12,
      longitude: -77,
      geometry: null,
    };
    expect(spatialPoint(centroid)).toBeNull();
    expect(canReuseCandidate(centroid)).toBe(false);
    expect(canReuseCandidate(candidate)).toBe(true);
  });
  it("keeps real point results as point markers", async () => {
    render(
      <LocationMap
        latitude={-12}
        longitude={-77}
        precision="PUERTA"
        geometry={{ type: "Point", coordinates: [-77, -12] }}
        candidates={[]}
      />,
    );
    await waitFor(() => expect(mapCalls.marker).toHaveBeenCalledOnce());
    expect(mapCalls.source).not.toHaveBeenCalled();
    expect(
      screen.queryByRole("link", { name: "OpenStreetMap contributors" }),
    ).not.toBeInTheDocument();
  });
  it.each([
    { source: "OpenStreetMap / Geofabrik", evidence: [] },
    {
      source: "CATALOGO_DIRECCIONES_VALIDADAS",
      evidence: [{ original_source: "OSM_WAY" }],
    },
  ])(
    "attributes source and inherited evidence without adding a remote basemap",
    async (provenance) => {
      render(
        <LocationMap
          latitude={null}
          longitude={null}
          precision="VIA"
          geometry={line}
          candidates={[{ ...candidate, ...provenance }]}
        />,
      );
      expect(
        screen.getByRole("link", { name: "OpenStreetMap contributors" }),
      ).toHaveAttribute("href", "https://www.openstreetmap.org/copyright");
      expect(
        screen.getByText("WGS84 · Sin cartografía base"),
      ).toBeInTheDocument();
      await waitFor(() => expect(mapCalls.source).toHaveBeenCalledOnce());
      expect(mapCalls.source.mock.calls[0][1].type).toBe("geojson");
    },
  );
});
