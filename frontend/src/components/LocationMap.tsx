import { useEffect, useRef, useState } from "react";
import { MapPin } from "lucide-react";
import type { Candidate, MapContext, SpatialGeometry } from "../types";
import { request } from "../lib/api";
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
  runId,
  ubigeo,
  resultMethod,
  coordinateWarnings,
}: {
  latitude: number | null;
  longitude: number | null;
  candidates: Candidate[];
  selectedCandidateId?: string;
  geometry?: SpatialGeometry | null;
  precision: string;
  runId?: string;
  ubigeo?: string;
  resultMethod?: string;
  coordinateWarnings?: unknown[];
}) {
  const container = useRef<HTMLDivElement>(null);
  const [failed, setFailed] = useState(false);
  const [context, setContext] = useState<MapContext | null>(null);
  const [contextError, setContextError] = useState(false);
  const [contextLoading, setContextLoading] = useState(false);
  const isSourceCoordinate = (method: string) =>
    ["COORD_ORIGINAL", "COORD_TEXTO"].includes(method);
  const conflictingCoordinates =
    /COORDENADAS_CONTRADICTORIAS|CRS_CONFLICTIVO/.test(
      JSON.stringify([
        coordinateWarnings ?? [],
        ...candidates
          .filter((candidate) => isSourceCoordinate(candidate.method))
          .map((candidate) => candidate.evidence),
      ]),
    );
  const hiddenCandidates = candidates.filter(
    (candidate) =>
      isSourceCoordinate(candidate.method) &&
      (conflictingCoordinates ||
        /CRS_NO_CONFIRMADO|CRS_CONFLICTIVO/.test(
          JSON.stringify(candidate.evidence),
        )),
  );
  const omitResult =
    isSourceCoordinate(resultMethod ?? "") &&
    (conflictingCoordinates || hiddenCandidates.length > 0);
  const hasLocation =
    candidates.some(
      (candidate) =>
        !hiddenCandidates.includes(candidate) &&
        (!!spatialPoint(candidate) || isAreaGeometry(candidate.geometry)),
    ) ||
    (!omitResult &&
      (!!spatialPoint({ latitude, longitude, geometry, precision }) ||
        isAreaGeometry(geometry)));
  useEffect(() => {
    setContext(null);
    setContextError(false);
    if (!runId || !ubigeo || !/^\d{6}$/.test(ubigeo)) {
      setContextLoading(false);
      return;
    }
    const controller = new AbortController();
    setContextLoading(true);
    request<MapContext>(
      `/runs/${encodeURIComponent(runId)}/map-context?ubigeo=${encodeURIComponent(ubigeo)}`,
      { signal: controller.signal },
    )
      .then((data) => {
        if (!controller.signal.aborted) setContext(data);
      })
      .catch(() => {
        if (!controller.signal.aborted) setContextError(true);
      })
      .finally(() => {
        if (!controller.signal.aborted) setContextLoading(false);
      });
    return () => controller.abort();
  }, [runId, ubigeo]);
  const usesOpenStreetMap =
    /openstreetmap|geofabrik|(?:^|[^a-z])osm(?:$|[^a-z])/i.test(
      (context?.sources ?? []).join(" "),
    ) ||
    candidates.some((candidate) =>
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
          const contextColor = theme.getPropertyValue("--map-context").trim();
          const items = [
            ...candidates
              .filter((candidate) => !hiddenCandidates.includes(candidate))
              .map((c) => ({
                ...c,
                color:
                  c.id === selectedCandidateId ? resultColor : candidateColor,
              })),
            {
              latitude: omitResult ? null : latitude,
              longitude: omitResult ? null : longitude,
              precision,
              geometry: omitResult ? null : geometry,
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
          const contextFeatures = context?.features ?? [];
          const framePositions = positions.length
            ? positions
            : contextFeatures.flatMap((feature) =>
                geometryPositions(feature.geometry),
              );
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
              center: framePositions[0] ?? [-75, -9],
              zoom: framePositions.length ? 14 : 4,
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
            framePositions.forEach((position) => bounds.extend(position));
            map.on("load", () => {
              if (disposed) return;
              if (contextFeatures.length) {
                map.addSource("local-context", {
                  type: "geojson",
                  data: {
                    type: "FeatureCollection",
                    features: contextFeatures,
                  },
                });
                map.addLayer({
                  id: "local-context-areas",
                  type: "fill",
                  source: "local-context",
                  filter: ["==", ["geometry-type"], "Polygon"],
                  paint: { "fill-color": contextColor, "fill-opacity": 0.08 },
                });
                map.addLayer({
                  id: "local-context-lines",
                  type: "line",
                  source: "local-context",
                  paint: {
                    "line-color": contextColor,
                    "line-width": 1.3,
                    "line-opacity": 0.65,
                  },
                });
              }
              if (!features.length) return;
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
            if (framePositions.length > 1)
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
    context,
    omitResult,
    conflictingCoordinates,
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
        <div className="map-caption">
          {contextLoading
            ? "Cargando contexto local…"
            : contextError
              ? "Contexto local no disponible · Sin cartografía base"
              : context?.features.length
                ? `Contexto local del catálogo${context.truncated ? " · Cobertura parcial" : ""}`
                : "WGS84 · Sin cartografía base"}
        </div>
      </div>
      <div className="map-legend" aria-label="Leyenda del visor">
        {(hiddenCandidates.length > 0 || omitResult) && (
          <span>
            Coordenadas originales sin CRS confirmado o contradictorias: se
            conservan en la ficha y no se dibujan.
          </span>
        )}
        {!!context?.features.length && !hasLocation && (
          <span>
            Vista del distrito como contexto; todavía no hay un lugar
            corroborado para mostrar.
          </span>
        )}
        <span>
          <i className="result-key" />
          Resultado o candidato seleccionado
        </span>
        {!!context?.features.length && (
          <span>
            <i className="context-key" />
            Contexto local · sin mapa base externo
          </span>
        )}
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
