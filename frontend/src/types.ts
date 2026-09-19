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
  config: Record<string, unknown>;
}
export interface Candidate {
  id: string;
  label: string;
  method: string;
  precision: string;
  latitude: number;
  longitude: number;
  score: number;
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
  accepted: number;
  unresolved: number;
  recent_runs: Run[];
}
