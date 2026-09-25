import { useEffect, useRef, useState } from "react";
import { MapPin } from "lucide-react";
import type { ExpressionSpecification } from "maplibre-gl";
import type { SpatialGeometry } from "../types";
import { geometryPositions } from "../lib/geometry";
import { label } from "../lib/format";
import "maplibre-gl/dist/maplibre-gl.css";
import workerUrl from "maplibre-gl/dist/maplibre-gl-worker.mjs?worker&url";

export const statisticLayers = {
  original: { label: "Coordenadas de origen", color: "#188261" },
  reference: { label: "Referencia geográfica", color: "#087bc1" },
  manual: { label: "Revisión manual", color: "#9a6709" },
  other: { label: "Otro método validado", color: "#765a9d" },
};
export type StatisticLayer = keyof typeof statisticLayers;
export interface StatisticsFeature {
  type: "Feature";
  id: string;
  geometry: SpatialGeometry;
  properties: {
    id: string;
    ubigeo: string;
    method: string;
    precision: string;
    layer: StatisticLayer;
  };
}

export function StatisticsMap({ features }: { features: StatisticsFeature[] }) {
  const container = useRef<HTMLDivElement>(null);
  const [failed, setFailed] = useState(false);
  const [renderedFeatures, setRenderedFeatures] = useState<
    StatisticsFeature[] | null
  >(null);
  const loading =
    features.length > 0 && !failed && renderedFeatures !== features;
  useEffect(() => {
    setFailed(false);
    setRenderedFeatures(null);
    if (!container.current || !features.length) return;
    let disposed = false;
    let cleanup: (() => void) | undefined;
    import("maplibre-gl")
      .then(({ Map, LngLatBounds, NavigationControl, Popup, setWorkerUrl }) => {
        if (disposed || !container.current) return;
        setWorkerUrl(workerUrl);
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
                  paint: { "background-color": "#eaf1f5" },
                },
              ],
            },
            center: [-75, -9],
            zoom: 4,
            attributionControl: false,
            locale: {
              "Map.Title": "Mapa local de resultados",
              "NavigationControl.ZoomIn": "Acercar",
              "NavigationControl.ZoomOut": "Alejar",
              "NavigationControl.ResetBearing": "Orientar al norte",
              "Popup.Close": "Cerrar detalle",
            },
          });
          map.addControl(
            new NavigationControl({ showCompass: false }),
            "top-left",
          );
          const bounds = new LngLatBounds();
          features.forEach((feature) =>
            geometryPositions(feature.geometry).forEach((position) =>
              bounds.extend(position),
            ),
          );
          map.on("load", () => {
            if (disposed) return;
            map.addSource("results", {
              type: "geojson",
              data: { type: "FeatureCollection", features },
            });
            const color: ExpressionSpecification = [
              "match",
              ["get", "layer"],
              "original",
              statisticLayers.original.color,
              "reference",
              statisticLayers.reference.color,
              "manual",
              statisticLayers.manual.color,
              statisticLayers.other.color,
            ];
            map.addLayer({
              id: "areas",
              type: "fill",
              source: "results",
              filter: ["==", ["geometry-type"], "Polygon"],
              paint: { "fill-color": color, "fill-opacity": 0.2 },
            });
            map.addLayer({
              id: "lines",
              type: "line",
              source: "results",
              filter: ["!=", ["geometry-type"], "Point"],
              paint: { "line-color": color, "line-width": 2 },
            });
            map.addLayer({
              id: "points",
              type: "circle",
              source: "results",
              filter: ["==", ["geometry-type"], "Point"],
              paint: {
                "circle-color": color,
                "circle-radius": 5,
                "circle-stroke-color": "#ffffff",
                "circle-stroke-width": 1.2,
              },
            });
            if (!bounds.isEmpty())
              map.fitBounds(bounds, { padding: 40, maxZoom: 15, duration: 0 });
            // Creating the canvas does not mean the GeoJSON has been drawn.
            // Idle follows the source's worker processing and its final frame.
            map.once("idle", () => {
              if (!disposed) setRenderedFeatures(features);
            });
            for (const layer of ["areas", "lines", "points"]) {
              map.on("mouseenter", layer, () => {
                map.getCanvas().style.cursor = "pointer";
              });
              map.on("mouseleave", layer, () => {
                map.getCanvas().style.cursor = "";
              });
              map.on("click", layer, (event) => {
                const properties = event.features?.[0]?.properties;
                if (!properties) return;
                const content = document.createElement("div");
                const title = document.createElement("strong");
                title.textContent = `UBIGEO ${properties.ubigeo || "no declarado"}`;
                const detail = document.createElement("p");
                detail.textContent = `${label(properties.method)} · ${label(properties.precision)}`;
                const link = document.createElement("a");
                link.textContent = "Consultar ubicación";
                link.href = `/results/${encodeURIComponent(properties.id)}`;
                content.append(title, detail, link);
                new Popup({ maxWidth: "280px" })
                  .setLngLat(event.lngLat)
                  .setDOMContent(content)
                  .addTo(map);
              });
            }
          });
          map.on("error", () => {
            if (!disposed) setFailed(true);
          });
          cleanup = () => map.remove();
        } catch {
          if (!disposed) setFailed(true);
        }
      })
      .catch(() => {
        if (!disposed) setFailed(true);
      });
    return () => {
      disposed = true;
      cleanup?.();
    };
  }, [features]);
  return (
    <div
      className="statistics-map-frame"
      role="region"
      aria-label="Mapa interactivo de geometrías aceptadas"
      aria-busy={loading}
    >
      <div ref={container} className="statistics-map-canvas" />
      {loading && (
        <div className="statistics-map-empty" role="status">
          <MapPin size={30} aria-hidden="true" />
          <strong>Cargando geometrías del mapa…</strong>
          <span>Preparando los resultados geográficos aceptados.</span>
        </div>
      )}
      {(!features.length || failed) && (
        <div className="statistics-map-empty">
          <MapPin size={30} aria-hidden="true" />
          <strong>
            {failed
              ? "El visor no está disponible"
              : "Sin geometrías en esta vista"}
          </strong>
          <span>
            {failed
              ? "Puedes consultar todos los resultados en Detalle de registros."
              : "Cambia las capas o el distrito. Solo se muestran ubicaciones aceptadas con geometría válida."}
          </span>
        </div>
      )}
      <span className="statistics-map-caption">
        WGS84 · Geometrías locales · Sin cartografía base externa
      </span>
    </div>
  );
}
