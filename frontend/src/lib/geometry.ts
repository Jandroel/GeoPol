import type { Candidate, SpatialGeometry } from "../types";

export const pointPrecisions = [
  "PUERTA",
  "INTERSECCION",
  "SITIO",
  "COORDENADA",
];
export const areaPrecisions = ["VIA", "CUADRA", "MANZANA", "NUCLEO"];
export const isAreaPrecision = (precision: string) =>
  areaPrecisions.includes(precision);
export const isAreaGeometry = (geometry?: SpatialGeometry | null) =>
  !!geometry &&
  ["LineString", "MultiLineString", "Polygon", "MultiPolygon"].includes(
    geometry.type,
  );
export const geometryLabel = (geometry?: SpatialGeometry | null) => {
  if (!geometry) return "Sin geometría disponible";
  if (["LineString", "MultiLineString"].includes(geometry.type))
    return "Tramo de referencia";
  if (["Polygon", "MultiPolygon"].includes(geometry.type))
    return "Área de referencia";
  return "Punto de referencia";
};
export function geometryPositions(
  geometry?: SpatialGeometry | null,
): [number, number][] {
  const points: [number, number][] = [];
  function visit(value: unknown) {
    if (!Array.isArray(value)) return;
    if (typeof value[0] === "number") {
      if (
        Number.isFinite(value[0]) &&
        Number.isFinite(value[1]) &&
        Math.abs(value[0]) <= 180 &&
        Math.abs(value[1]) <= 90
      )
        points.push([value[0], value[1]]);
      return;
    }
    value.forEach(visit);
  }
  if (geometry) visit(geometry.coordinates);
  return points;
}
export function spatialPoint(value: {
  latitude: number | null;
  longitude: number | null;
  precision: string;
  geometry?: SpatialGeometry | null;
}): [number, number] | null {
  // An area/tramo may carry a legacy centroid. Never render it as a point.
  if (isAreaPrecision(value.precision) || isAreaGeometry(value.geometry))
    return null;
  if (
    value.latitude !== null &&
    value.longitude !== null &&
    Number.isFinite(value.latitude) &&
    Number.isFinite(value.longitude) &&
    Math.abs(value.latitude) <= 90 &&
    Math.abs(value.longitude) <= 180
  )
    return [value.longitude, value.latitude];
  if (value.geometry?.type === "Point")
    return geometryPositions(value.geometry)[0] ?? null;
  return null;
}
export function canReuseCandidate(candidate?: Candidate) {
  return (
    !!candidate &&
    ((pointPrecisions.includes(candidate.precision) &&
      !!spatialPoint(candidate)) ||
      (isAreaGeometry(candidate.geometry) &&
        geometryPositions(candidate.geometry).length > 1))
  );
}
