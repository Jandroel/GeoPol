import { useEffect, useRef, useState } from "react";
import { MapPin } from "lucide-react";
import type { Candidate } from "../types";
import "maplibre-gl/dist/maplibre-gl.css";

export default function LocationMap({
  latitude,
  longitude,
  candidates,
}: {
  latitude: number | null;
  longitude: number | null;
  candidates: Candidate[];
}) {
  const container = useRef<HTMLDivElement>(null);
  const [failed, setFailed] = useState(false);
  useEffect(() => {
    if (!container.current) return;
    let disposed = false;
    let cleanup: (() => void) | undefined;
    import("maplibre-gl")
      .then(({ Map, Marker, Popup, NavigationControl, LngLatBounds }) => {
        if (disposed || !container.current) return;
        const points = [
          ...(latitude !== null && longitude !== null
            ? [
                {
                  latitude,
                  longitude,
                  label: "Ubicación resultante",
                  color: "#117d77",
                },
              ]
            : []),
          ...candidates
            .filter(
              (c) =>
                Number.isFinite(c.latitude) && Number.isFinite(c.longitude),
            )
            .map((c) => ({ ...c, color: "#be841f" })),
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
                  paint: { "background-color": "#edf1ef" },
                },
              ],
            },
            center: points.length
              ? [points[0].longitude, points[0].latitude]
              : [-75, -9],
            zoom: points.length ? 14 : 4,
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
          for (const point of points) {
            const popupText = document.createElement("span");
            popupText.textContent = point.label;
            const marker = new Marker({ color: point.color })
              .setLngLat([point.longitude, point.latitude])
              .setPopup(new Popup().setDOMContent(popupText))
              .addTo(map);
            marker.getElement().setAttribute("aria-label", point.label);
            bounds.extend([point.longitude, point.latitude]);
          }
          if (points.length > 1)
            map.fitBounds(bounds, { padding: 65, maxZoom: 16, duration: 0 });
          map.on("error", () => setFailed(true));
          cleanup = () => map.remove();
        } catch {
          setFailed(true);
        }
      })
      .catch(() => setFailed(true));
    return () => {
      disposed = true;
      cleanup?.();
    };
  }, [latitude, longitude, candidates]);
  return (
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
            El visor necesita WebGL. Las coordenadas siguen disponibles en la
            ficha.
          </p>
        </div>
      )}
      <div className="map-label">
        <span className="tiny-dot" />
        Cartografía base no configurada
      </div>
      <div className="map-caption">
        WGS84 · Vista local sin servicios cartográficos externos
      </div>
    </div>
  );
}
