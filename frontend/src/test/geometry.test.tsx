import { render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import LocationMap from "../components/LocationMap";
import { canReuseCandidate, spatialPoint } from "../lib/geometry";
import type { Candidate, SpatialGeometry } from "../types";

const mapCalls = vi.hoisted(() => ({
  source: vi.fn(),
  layer: vi.fn(),
  marker: vi.fn(),
  bounds: vi.fn(),
  remove: vi.fn(),
}));
vi.mock("maplibre-gl", () => ({
  setWorkerUrl: vi.fn(),
  Map: class {
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
describe("real spatial geometry rendering", () => {
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
