# MVP implementation contract

Backend: FastAPI + SQLAlchemy, persistent SQL job queue, dedicated worker. PostgreSQL/PostGIS deployment; SQLite supports local development. API prefix `/api`. Bearer session authentication. All list endpoints return `{items, total, page, page_size}`. Dates ISO UTC. Errors `{detail: string}` (validation may use FastAPI list). Roles admin, operator, reviewer, analyst. No real data committed.

## Domain interface (owned by domain implementation)

`domain/normalization.py`: `normalize_record(raw: dict, mapping: dict | None = None) -> dict`. Canonical components: complaint_id, location_original, location_normalized, ubigeo, district, street_type, street_name, door_number, block_number, cross_street, site_name, urban_core, latitude, longitude, coordinate_origin, transformations (list), warnings (list), legacy (dict). xx latitude and yy longitude for SIDPOL. Forced centroid never accepted as original.

`domain/matching.py`: `resolve_location(normalized: dict, features: list[dict], reference_available: bool) -> dict` returns resolution, method, precision, evidence_band, product, latitude, longitude, reason, candidates(list), attempts(list). Each candidate includes id (feature identifier or stable key), label, method, precision, latitude, longitude, score, evidence(list). No invented probability. Reference feature format: id, kind (door/block/manzana/street/intersection/site/nucleus/jurisdiction/boundary), ubigeo, street_type, street_name, door_number, block_number, cross_street, name, latitude, longitude, geometry(optional GeoJSON), source, version. Return review on unresolved ambiguity and unknown territory. Rule 2026.3 supports exact/explicit-alias and guarded strong fuzzy matches, distinguishing Point results from real line/polygon results. Similarity is not a probability. No reference required to extract coordinates, but territorial corroboration required to autoaccept; plausible coordinates without boundary remain review.

`domain/ingestion.py`: `inspect_file(path: Path, filename: str, sheet: str | None=None) -> dict` with columns, sheets, suggested_mapping, sample (at most 5 location-only fields), warnings. `iter_records(path: Path, filename: str, sheet: str | None=None, delimiter: str=',', encoding: str='utf-8-sig') -> Iterator[tuple[int, dict, str | None]]` yields logical ordinal starting 1, raw dict, issue (null if good). Bounded CSV/XLSX; preserve malformed recoverable rows as issues; raise explicit error on unrecoverable parser boundary. Domain may add helpers. Dependencies openpyxl, rapidfuzz, shapely. Tests own `tests/test_domain*.py`.

## API and UI

POST /auth/login {username,password} -> {token,user:{id,username,role}}. GET /auth/me -> user. POST /auth/logout -> {ok}.

GET /dashboard -> {runs,source_rows,location_units,review_required,review_open,review_actionable,accepted,unresolved,recent_runs:[run]}. runs and recent_runs retain history; other counts include only completed, current runs (superseded_by null). review_required is geographic resolution; review_open and review_actionable count pending tasks.

POST /uploads {filename,size} -> upload {id,filename,size,offset,status}. GET /uploads/{id} same. PATCH /uploads/{id} binary body, header Upload-Offset, bounded chunk <=8MiB -> upload. POST /uploads/{id}/complete -> upload plus sha256, profile. Profile uses header/bounded sample only. Bad sheet can be selected at run creation.

GET /uploads/{id}/profile?sheet=&delimiter=&encoding= -> refreshed profile for a completed upload, scoped to its owner/admin. GET /uploads/{id}/download -> immutable original with permission check and audit. Source columns for exports follow the selected worksheet and parsing configuration.

POST /runs {upload_id,name,sheet?,mapping?:{canonical:source column},delimiter?:',',encoding?:'utf-8-sig',reference_id?:string,crs?:'EPSG:4326'} -> run. GET /runs -> list. GET /runs/{id} -> run incl counters/status/error. POST /runs/{id}/cancel -> run. POST /runs/{id}/retry -> run (resume failed/cancelled same rules). POST /runs/{id}/reprocess with optional {reference_id?:string|null,crs?:'EPSG:4326'|null} -> new run, same file/config, current rules and independent results. Omit property/body to keep catalog; null clears it. Response includes parent_run_id/superseded_by. Only a successful child supersedes its parent; historical versions remain readable but not editable.

run = {id,name,status,filename,created_at,started_at,finished_at,source_rows,location_units,processed_units,issue_rows,reference_id,rules_version,error,config,counts:{resolution:count},counts_by_product:{product:count}}. counts_by_product counts only ACEPTADO_AUTOMATICO. Status QUEUED/INGESTING/PROCESSING/COMPLETED/COMPLETED_WITH_ISSUES/FAILED/CANCELLED.

GET /runs/{id}/results?page=1&page_size=25&resolution=&q= -> list of result. GET /results/{id} -> result incl normalized, transformations, attempts, candidates, history, source_row_count. result = {id,run_id,complaint_id,location_original,location_normalized,ubigeo,resolution,method,precision,evidence_band,product,latitude,longitude,reason,revision,manual,review_owner,review_expires_at}. Original entire source rows NOT sent to UI.

POST /results/{id}/claim -> result. POST /results/{id}/decisions {expected_revision,action:'accept_candidate'|'manual_point'|'address_only'|'unresolved'|'reopen',candidate_id?,latitude?,longitude?,precision?,address?,reason,evidence?} -> result. Must claim first. Version conflict409. Keep audit and immutable revisions. Manual point evidence required. Review owner allowed admin/reviewer. GET /review? page/size/q -> list results pending review.

Results also include review_status (OPEN/CLOSED), review_bucket (actionable/needs_reference/needs_data/technical/none), and candidate_count. Manual unresolved decisions close the task; reopen restores OPEN without erasing manual history. POST /results/{id}/release releases only the caller's reservation; an already free case is idempotent.

GET /review filters: page/page_size/q, run_id, bucket (all/actionable/needs_reference/needs_data/technical; default all), stage (open/closed/all; default open), include_superseded (default false). Only completed runs are reviewable. GET /review/summary applies run_id/q/include_superseded and returns {open:{actionable,needs_reference,needs_data,technical},closed,total}. GET /review/next applies the same filters plus exclude_id and returns {item:result|null}; it selects only current OPEN cases, skips other reviewers' active reservations and does not claim anything. Closed-stage queries return null.

GET /references -> list. POST /references multipart form fields name,version,source,file (CSV or FeatureCollection GeoJSON, finite documented catalog limit; uploaded files stay private) -> {id,name,version,source,feature_count,sha256}. GET /references/{id} -> metadata. GeoJSON properties match domain feature fields. No demo autoimport. UI separate catalogue page.

POST /runs/{id}/exports {profile:'locations'|'source_rows',safe_spreadsheet:true} -> {id,status,run_id}. GET /exports/{id} -> {id,status,error,filename,row_count,sha256}. GET /exports/{id}/download -> file authenticated fetch; GET /exports/{id}/manifest -> JSON. Async snapshot export must include unresolved rows. CSV coordinates null when unresolved. Source-row export can access restricted originals for admin/operator only; analyst default location export excludes PII.

New exports use manifest schema_version 2 and append GEOPOL_review_status/GEOPOL_review_bucket. Pending v1 exports retain the v1 columns. Older immutable revisions without queue state export empty values for those fields; historical snapshots are never rewritten.

GET /audit?page=1&page_size=25 -> list audit {id,actor,action,entity_id,created_at,detail}; admin only. GET /rules -> {version,policies,limitations}. GET /health -> {status,version,database}.

GET /health/worker -> {status,last_seen_at}, authenticated. The rule version has one canonical constant: `domain.RULES_VERSION`; a worker refuses a run created for an unavailable rules version. Original coordinates require a confirmed EPSG:4326 input CRS; each reference has its own validated CRS. Geocoding address text does not require an input CRS. Declared coordinate conflicts require review or rejection, never an implicit reprojection.

GET /health verifies migrations.SCHEMA_VERSION (currently 3) and also returns schema_version. Rule version 2026.3 retains audited normalization and adds the geometric and reusable-address contracts below; unresolved conflicts still require review.

## Frontend

React TS Vite, React Router, TanStack Query, lucide-react, MapLibre (local blank style, no network basemap). Spanish operational UI. Dashboard, upload/run wizard, run detail/progress, results filters, review detail/map/history, reference import, exports, rules. Vite proxy /api to localhost8000. Container static frontend behind nginx proxy backend. Tokens held only in memory/sessionStorage; login explicit, no known default password. Include accessible responsive polished design, loading/error/empty states and real API integration. Empty state can download synthetic demo CSV from public/demo.csv. No mock progress or invented live data.


## Version 2026.3 geometry and validated addresses

Location results and candidates include `geometry` (GeoJSON or null). Accepted `PUNTO` uses a Point with latitude/longitude; `AREA_TRAMO` keeps a LineString/MultiLineString/Polygon/MultiPolygon and null latitude/longitude. Precision identifies VIA, CUADRA, MANZANA, NUCLEO or SITIO as applicable; no centroid is generated. New schema-3 exports append `GEOPOL_geometry` containing JSON. Pending schema-1/2 exports retain their original columns and snapshots.

`DecisionInput.learn_address` defaults false. A reviewer can explicitly reuse a confirmed candidate or manual point with a known precision, address and territory. Address memory matches the complete normalized address/components and UBIGEO, independently of complaint IDs. Only active records from a still-current manual revision created before the new run are considered. Conflicting confirmations and fresh contradictory evidence require review. Memory candidates retain original cartographic provenance and the memory ID/source revision. Changes or reopening retire the originating memory. `address_only` renormalizes corrected components and clears obsolete candidates; raw source rows and earlier revisions stay intact.

POST `/api/address-memory/{id}/revoke` with `{reason:string}` (minimum 8 characters), reviewer/admin, deactivates future reuse without modifying completed results. This also works when the source run has been superseded. No prior manual decisions are retroactively promoted into memory.

Territorial reference retrieval indexes primary names and explicit aliases, ranks fuzzy alternatives before retrieving features and preserves competitors. It no longer takes the first 500 district features by ID. Bounds are 64 matching keys per input name, 512 primary lookup keys, 2,000 retrieved features and 24 MiB of payload; a truncated search cannot autoaccept. Catalogs are immutable, source-specific feature versions survive import, and source/build manifests identify the selected data.
