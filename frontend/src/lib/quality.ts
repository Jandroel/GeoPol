export const qualityFlagLabels: Record<number, string> = {
  1: "Flag 1 · Puerta, cuadra, cruce o coordenadas",
  2: "Flag 2 · Núcleo y distrito / vía y jurisdicción",
};
export const reviewStateLabels = {
  automatic: "Automático",
  quick_review: "Revisión rápida",
  detailed_review: "Revisión detallada",
  accepted_manual: "Aceptado manualmente",
  unmatched: "Sin coincidencia",
  reference_pending: "Referencia pendiente",
  unprocessed: "Pendiente de procesamiento",
};
export const qualityStageLabels: Record<string, string> = {
  door: "Puertas",
  block: "Cuadras",
  intersection: "Cruces de vías",
  street: "Vías",
  nucleus: "Núcleos y centros poblados",
  jurisdiction: "Jurisdicciones",
};
export const qualityFlagLabel = (flag?: number | null) =>
  flag == null
    ? "Sin flag asignado"
    : (qualityFlagLabels[flag] ?? `Flag ${flag}`);
export const reviewStateLabel = (state?: string | null) =>
  state
    ? (reviewStateLabels[state as keyof typeof reviewStateLabels] ?? state)
    : "Estado no evaluado";
export const qualityStageLabel = (stage?: string | null) =>
  stage ? (qualityStageLabels[stage] ?? stage) : "Sin etapa";
export const percentage = (value: number, total: number) =>
  `${new Intl.NumberFormat("es-PE", { maximumFractionDigits: 1 }).format(total ? (value / total) * 100 : 0)} %`;
