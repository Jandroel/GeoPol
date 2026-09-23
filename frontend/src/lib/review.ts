import { reviewStateLabels } from "./quality";
export const reviewBuckets = {
  actionable: {
    label: "Revisión accionable",
    description: "Candidatos o evidencia que requieren una decisión.",
  },
  needs_reference: {
    label: "Referencia pendiente",
    description: "Requiere catálogo o cobertura territorial antes de decidir.",
  },
  needs_data: {
    label: "Datos por completar",
    description:
      "Falta información de ubicación que debe verificarse en la fuente.",
  },
  technical: {
    label: "Atención técnica",
    description: "Requiere resolver un problema del procesamiento.",
  },
} as const;
export type ReviewBucket = keyof typeof reviewBuckets;
export function reservationIsLive(
  expiresAt: string | undefined,
  now = Date.now(),
) {
  if (!expiresAt) return false;
  const utc = /Z$|[+-]\d\d:\d\d$/.test(expiresAt) ? expiresAt : `${expiresAt}Z`;
  return Date.parse(utc) > now;
}
export interface ReviewFilters {
  runId: string;
  bucket: ReviewBucket | "all";
  stage: "open" | "closed" | "all";
  q: string;
  page: number;
  includeSuperseded: boolean;
  qualityFlag?: string;
  qualityStage?: string;
  reviewState?: string;
}
export function readReviewFilters(params: URLSearchParams): ReviewFilters {
  const bucket = params.get("bucket") ?? "actionable";
  const stage = params.get("stage") ?? "open";
  const page = Number(params.get("page") ?? 1);
  return {
    runId: params.get("run_id") ?? "",
    bucket:
      bucket === "all" || Object.hasOwn(reviewBuckets, bucket)
        ? (bucket as ReviewFilters["bucket"])
        : "actionable",
    stage: ["open", "closed", "all"].includes(stage)
      ? (stage as ReviewFilters["stage"])
      : "open",
    q: (params.get("q") ?? "").slice(0, 100),
    page: Number.isSafeInteger(page) && page > 0 ? page : 1,
    includeSuperseded: params.get("include_superseded") === "true",
    qualityFlag: ["1", "2"].includes(params.get("quality_flag") ?? "")
      ? params.get("quality_flag")!
      : "",
    reviewState: Object.hasOwn(
      reviewStateLabels,
      params.get("review_state") ?? "",
    )
      ? params.get("review_state")!
      : "",
    qualityStage: [
      "door",
      "block",
      "intersection",
      "street",
      "nucleus",
      "jurisdiction",
    ].includes(params.get("quality_stage") ?? "")
      ? params.get("quality_stage")!
      : "",
  };
}
export function reviewParams(filters: ReviewFilters) {
  const params = new URLSearchParams({
    bucket: filters.bucket,
    stage: filters.stage,
    page: String(filters.page),
    page_size: "25",
    include_superseded: String(filters.includeSuperseded),
  });
  if (filters.runId) params.set("run_id", filters.runId);
  if (filters.q) params.set("q", filters.q);
  if (filters.qualityFlag) params.set("quality_flag", filters.qualityFlag);
  if (filters.qualityStage) params.set("quality_stage", filters.qualityStage);
  if (filters.reviewState) params.set("review_state", filters.reviewState);
  return params;
}
export function validReviewReturn(value: string | null, runId: string) {
  // Only internal, known screens may be used as a return destination.
  if (value && /^\/review(?:\?|$)/.test(value)) return value;
  if (value && /^\/runs\/[a-zA-Z0-9-]+(?:\?|$)/.test(value)) return value;
  return `/runs/${runId}`;
}
export function nextReviewParams(
  returnPath: string,
  runId: string,
  excludeId: string,
) {
  const filters = returnPath.startsWith("/review")
    ? readReviewFilters(new URLSearchParams(returnPath.split("?")[1] ?? ""))
    : {
        runId,
        bucket: "actionable" as const,
        stage: "open" as const,
        q: "",
        page: 1,
        includeSuperseded: false,
      };
  const params = reviewParams({ ...filters, stage: "open", page: 1 });
  params.set("exclude_id", excludeId);
  return params;
}
const reasons: Record<string, string> = {
  MEMORIA_DIRECCION_VALIDADA:
    "Coincidencia con una dirección validada previamente mediante revisión documentada.",
  REFERENCIA_NO_DISPONIBLE_O_POLITICA_NO_CONFIRMADA:
    "No hay una referencia evaluable para resolver esta ubicación.",
  REFERENCIA_NO_DISPONIBLE: "Falta una fuente de referencia.",
  TERRITORIO_NO_CONFIRMADO:
    "El territorio de la ubicación necesita corroboración.",
  MULTIPLES_CANDIDATOS:
    "Hay más de un candidato compatible; compara la evidencia.",
  BUSQUEDA_COMPLETADA_SIN_COINCIDENCIA:
    "La búsqueda terminó sin una coincidencia.",
  BUSQUEDA_REFERENCIAL_TRUNCADA:
    "La búsqueda alcanzó su límite; requiere revisar la cobertura.",
  DIRECCION_INSUFICIENTE: "La dirección no aporta información suficiente.",
  COINCIDENCIA_UNICA_CON_EVIDENCIA_TERRITORIAL:
    "Coincidencia única respaldada por evidencia territorial.",
};
export const reviewReason = (reason: string) => {
  if (reason.startsWith("MEMORIA:"))
    return `Referencia de validación: ${reason.slice(8)}`;
  if (reason.startsWith("REVISION_ORIGEN:"))
    return `Revisión de origen: ${reason.slice(16)}`;
  return reasons[reason] ?? reason.replaceAll("_", " ");
};
