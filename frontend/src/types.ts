export interface User {
  id: string;
  username: string;
  role: "admin" | "operator" | "reviewer" | "analyst";
}
export interface Page<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
}
export type SpatialGeometry =
  | { type: "Point"; coordinates: number[] }
  | { type: "LineString" | "MultiPoint"; coordinates: number[][] }
  | { type: "MultiLineString" | "Polygon"; coordinates: number[][][] }
  | { type: "MultiPolygon"; coordinates: number[][][][] };
export interface Run {
  id: string;
  name: string;
  status: string;
  filename: string;
  created_at: string;
  started_at?: string;
  finished_at?: string;
  source_rows: number;
  location_units: number;
  processed_units: number;
  issue_rows: number;
  reference_id?: string;
  rules_version: string;
  error?: string;
  counts: Record<string, number>;
  /** Product counts restricted to ACEPTADO_AUTOMATICO results. */
  counts_by_product?: Record<string, number>;
  config: Record<string, unknown>;
  parent_run_id?: string | null;
  superseded_by?: string | null;
}
export interface Candidate {
  id: string;
  label: string;
  method: string;
  precision: string;
  latitude: number | null;
  longitude: number | null;
  geometry?: SpatialGeometry | null;
  source?: string;
  version?: string;
  score: number | null;
  evidence: unknown[];
}
export interface LocationResult {
  id: string;
  run_id: string;
  complaint_id: string;
  location_original: string;
  location_normalized: string;
  ubigeo: string;
  resolution: string;
  method: string;
  precision: string;
  evidence_band: string;
  product: string;
  latitude: number | null;
  longitude: number | null;
  geometry?: SpatialGeometry | null;
  reason: string;
  revision: number;
  manual: boolean;
  review_owner?: string;
  review_expires_at?: string;
  normalized?: Record<string, unknown>;
  transformations?: unknown[];
  attempts?: unknown[];
  candidates?: Candidate[];
  history?: Record<string, unknown>[];
  source_row_count?: number;
  review_status: "OPEN" | "CLOSED";
  review_bucket:
    "actionable" | "needs_reference" | "needs_data" | "technical" | "none";
  candidate_count: number;
}
export interface ReviewSummary {
  open: Record<
    "actionable" | "needs_reference" | "needs_data" | "technical",
    number
  >;
  closed: number;
  total: number;
}
export interface Reference {
  id: string;
  name: string;
  version: string;
  source: string;
  feature_count: number;
  sha256: string;
}
export interface Profile {
  columns: string[];
  sheets: string[];
  suggested_mapping: Record<string, string>;
  warnings: string[];
  sample?: Record<string, unknown>[];
  sheet?: string;
  delimiter?: string;
  encoding?: string;
}
export interface Upload {
  id: string;
  filename: string;
  size: number;
  offset: number;
  status: string;
  profile?: Profile;
  sha256?: string;
}
export interface ExportJob {
  id: string;
  status: string;
  run_id?: string;
  error?: string;
  filename?: string;
  row_count?: number;
  sha256?: string;
}
export interface Dashboard {
  runs: number;
  source_rows: number;
  location_units: number;
  review_required: number;
  review_open: number;
  review_actionable: number;
  accepted: number;
  unresolved: number;
  recent_runs: Run[];
}
