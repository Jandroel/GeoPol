export const number = (value: number | undefined) =>
  new Intl.NumberFormat("es-PE").format(value ?? 0);
export const date = (value?: string) =>
  value
    ? new Intl.DateTimeFormat("es-PE", {
        dateStyle: "medium",
        timeStyle: "short",
      }).format(
        new Date(
          value.endsWith("Z") || /[+-]\d\d:\d\d$/.test(value)
            ? value
            : `${value}Z`,
        ),
      )
    : "—";
const labels: Record<string, string> = {
  QUEUED: "En cola",
  INGESTING: "Leyendo archivo",
  PROCESSING: "Procesando",
  COMPLETED: "Completado",
  COMPLETED_WITH_ISSUES: "Con incidencias",
  FAILED: "Fallido",
  CANCELLED: "Cancelado",
  ACCEPTED: "Aceptado",
  REVIEW_REQUIRED: "Requiere revisión",
  REVIEW: "En revisión",
  UNRESOLVED: "Sin resolver",
  ADDRESS_ONLY: "Solo dirección",
  accepted: "Aceptado",
  review: "En revisión",
  review_required: "Requiere revisión",
  unresolved: "Sin resolver",
  address_only: "Solo dirección",
  admin: "Administrador",
  operator: "Operador",
  reviewer: "Revisor",
  analyst: "Analista",
};
Object.assign(labels, {
  ACEPTADO_AUTOMATICO: "Aceptado automáticamente",
  ACEPTADO_MANUAL: "Aceptado por revisión",
  REVISION_REQUERIDA: "Requiere revisión",
  SIN_COINCIDENCIA: "Sin coincidencia",
  INFORMACION_INSUFICIENTE: "Información insuficiente",
  NO_EVALUABLE_REFERENCIA: "Sin referencia evaluable",
  ERROR_TECNICO: "Error técnico",
  EXCLUIDO_FLAG_10: "Excluido por FLAG 10",
  PUNTO: "Punto",
  AREA_TRAMO: "Área o tramo",
  MANZANA: "Manzana",
  DIRECCION_VALIDADA: "Dirección validada previamente",
  DIRECCION_SIN_PUNTO: "Dirección sin punto",
  NINGUNO: "Sin producto",
  ALTA: "Alta",
  REVISION: "Revisión",
  SIN_EVIDENCIA: "Sin evidencia",
});
export const label = (value?: string | null) =>
  value
    ? (labels[value] ?? value.replaceAll("_", " ").toLowerCase())
    : "Sin determinar";
export const isActiveRun = (status?: string) =>
  ["QUEUED", "INGESTING", "PROCESSING"].includes(status ?? "");
export const displayValue = (value: unknown) =>
  typeof value === "object"
    ? JSON.stringify(value, null, 2)
    : String(value ?? "—");
