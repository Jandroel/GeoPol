import { useEffect, useRef, useState } from "react";
import { MapPin } from "lucide-react";
import type { Candidate, SpatialGeometry } from "../types";
import {
  geometryPositions,
  isAreaGeometry,
  spatialPoint,
} from "../lib/geometry";
import "maplibre-gl/dist/maplibre-gl.css";
import workerUrl from "maplibre-gl/dist/maplibre-gl-worker.mjs?worker&url";

export default function LocationMap({
  latitude,
  longitude,
  candidates,
  selectedCandidateId,
  geometry,
  precision,
}: {
  latitude: number | null;
  longitude: number | null;
  candidates: Candidate[];
  selectedCandidateId?: string;
  geometry?: SpatialGeometry | null;
  precision: string;
}) {
  const container = useRef<HTMLDivElement>(null);
  const [failed, setFailed] = useState(false);
  const usesOpenStreetMap = candidates.some((candidate) =>
    /openstreetmap|geofabrik|(?:^|[^a-z])osm(?:$|[^a-z])/i.test(
      `${candidate.source ?? ""} ${JSON.stringify(candidate.evidence ?? [])}`,
    ),
  );
  useEffect(() => {
    if (!container.current) return;
    let disposed = false;
    let cleanup: (() => void) | undefined;
    import("maplibre-gl")
      .then(
        ({
          Map,
          Marker,
          Popup,
          NavigationControl,
          LngLatBounds,
          setWorkerUrl,
        }) => {
          if (disposed || !container.current) return;
          // Vite must bundle the ESM worker and its shared dependencies locally.
          setWorkerUrl(workerUrl);
          const theme = getComputedStyle(document.documentElement);
          const resultColor = theme.getPropertyValue("--map-result").trim();
          const candidateColor = theme
            .getPropertyValue("--map-candidate")
            .trim();
          const backgroundColor = theme
            .getPropertyValue("--map-background")
            .trim();
          const items = [
            ...candidates.map((c) => ({
              ...c,
              color:
                c.id === selectedCandidateId ? resultColor : candidateColor,
            })),
            {
              latitude,
              longitude,
              precision,
              geometry,
              label: "Ubicación resultante",
              color: resultColor,
            },
          ];
          const points = items.flatMap((item) => {
            const position = spatialPoint(item);
            return position ? [{ ...item, position }] : [];
          });
          const features = items
            .filter(
              (item) =>
                isAreaGeometry(item.geometry) &&
                geometryPositions(item.geometry).length > 1,
            )
            .map((item) => ({
              type: "Feature" as const,
              geometry: item.geometry!,
              properties: { label: item.label, color: item.color },
            }));
          const positions = [
            ...points.map((point) => point.position),
            ...features.flatMap((feature) =>
              geometryPositions(feature.geometry),
            ),
          ];
          try {
            const map = new Map({
              container: container.current,
              style: {
                version: 8,
                sources: {},
                layers: [
                  {
                    id: "background",
                    type: "background",
                    paint: { "background-color": backgroundColor },
                  },
                ],
              },
              center: positions[0] ?? [-75, -9],
              zoom: positions.length ? 14 : 4,
              attributionControl: false,
              locale: {
                "Map.Title": "Visor espacial",
                "Marker.Title": "Ubicación",
                "NavigationControl.ZoomIn": "Acercar",
                "NavigationControl.ZoomOut": "Alejar",
                "NavigationControl.ResetBearing":
                  "Restablecer orientación al norte",
                "Popup.Close": "Cerrar detalle",
              },
            });
            map.addControl(
              new NavigationControl({ visualizePitch: false }),
              "top-right",
            );
            const bounds = new LngLatBounds();
            positions.forEach((position) => bounds.extend(position));
            map.on("load", () => {
              if (disposed || !features.length) return;
              map.addSource("reference-geometries", {
                type: "geojson",
                data: { type: "FeatureCollection", features },
              });
              map.addLayer({
                id: "reference-areas",
                type: "fill",
                source: "reference-geometries",
                filter: ["==", ["geometry-type"], "Polygon"],
                paint: { "fill-color": ["get", "color"], "fill-opacity": 0.2 },
              });
              map.addLayer({
                id: "reference-outlines",
                type: "line",
                source: "reference-geometries",
                paint: { "line-color": ["get", "color"], "line-width": 3 },
              });
            });
            for (const point of points) {
              const popupText = document.createElement("span");
              popupText.textContent = point.label;
              const marker = new Marker({ color: point.color })
                .setLngLat(point.position)
                .setPopup(new Popup().setDOMContent(popupText))
                .addTo(map);
              marker.getElement().setAttribute("aria-label", point.label);
            }
            if (positions.length > 1)
              map.fitBounds(bounds, { padding: 65, maxZoom: 16, duration: 0 });
            map.on("error", () => setFailed(true));
            cleanup = () => map.remove();
          } catch {
            setFailed(true);
          }
        },
      )
      .catch(() => setFailed(true));
    return () => {
      disposed = true;
      cleanup?.();
    };
  }, [
    latitude,
    longitude,
    candidates,
    selectedCandidateId,
    geometry,
    precision,
  ]);
  return (
    <>
      <div className="location-map">
        <div
          className="map-canvas"
          ref={container}
          aria-label="Visor espacial de la ubicación y sus candidatos"
        />
        {failed && (
          <div className="map-unavailable">
            <MapPin aria-hidden="true" />
            <p>
              El visor necesita WebGL. La geometría y su precisión siguen
              disponibles en la ficha.
            </p>
          </div>
        )}
        <div className="map-caption">WGS84 · Sin cartografía base</div>
      </div>
      <div className="map-legend" aria-label="Leyenda del visor">
        <span>
          <i className="result-key" />
          Resultado o candidato seleccionado
        </span>
        <span>
          <i className="candidate-key" />
          Otros candidatos
        </span>
        {usesOpenStreetMap && (
          <span className="map-attribution">
            ©{" "}
            <a
              className="inline-link"
              href="https://www.openstreetmap.org/copyright"
              target="_blank"
              rel="noopener noreferrer"
            >
              OpenStreetMap contributors
            </a>
          </span>
        )}
      </div>
    </>
  );
}
