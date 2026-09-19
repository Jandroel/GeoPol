import { lazy, Suspense, useState, type FormEvent } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useParams } from "react-router-dom";
import {
  ArrowLeft,
  Check,
  ClipboardCheck,
  History,
  LockKeyhole,
  MapPin,
} from "lucide-react";
import { useAuth } from "../auth";
import { post, request } from "../lib/api";
import { date, displayValue, label } from "../lib/format";
import type { LocationResult } from "../types";
import {
  Badge,
  Empty,
  ErrorNotice,
  Loading,
  Notice,
  PageHeader,
  Success,
} from "../components/ui";
const LocationMap = lazy(() => import("../components/LocationMap"));
const precisions = [
  "PUERTA",
  "INTERSECCION",
  "SITIO",
  "CUADRA",
  "NUCLEO",
  "VIA",
  "COORDENADA",
  "DESCONOCIDA",
];
export function ResultDetail() {
  const { id } = useParams();
  const { user } = useAuth();
  const client = useQueryClient();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>();
  const [success, setSuccess] = useState("");
  const [action, setAction] = useState("accept_candidate");
  const [candidate, setCandidate] = useState("");
  const [latitude, setLatitude] = useState("");
  const [longitude, setLongitude] = useState("");
  const [precision, setPrecision] = useState("COORDENADA");
  const [address, setAddress] = useState("");
  const [reason, setReason] = useState("");
  const [evidence, setEvidence] = useState("");
  const query = useQuery({
    queryKey: ["result", id],
    queryFn: () => request<LocationResult>(`/results/${id}`),
  });
  async function claim() {
    setBusy(true);
    setError(null);
    setSuccess("");
    try {
      const result = await post<LocationResult>(`/results/${id}/claim`);
      client.setQueryData<LocationResult>(["result", id], (previous) => ({
        ...previous,
        ...result,
      }));
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  }
  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!query.data) return;
    setBusy(true);
    setError(null);
    setSuccess("");
    try {
      const payload: Record<string, unknown> = {
        expected_revision: query.data.revision,
        action,
        reason,
      };
      if (action === "accept_candidate") payload.candidate_id = candidate;
      if (action === "manual_point") {
        payload.latitude = Number(latitude);
        payload.longitude = Number(longitude);
        payload.precision = precision;
        payload.evidence = evidence;
      }
      if (action === "address_only") payload.address = address;
      await post<LocationResult>(`/results/${id}/decisions`, payload);
      setSuccess(
        "Decisión registrada. La revisión anterior se conserva en el historial.",
      );
      setReason("");
      await client.invalidateQueries({ queryKey: ["result", id] });
      await client.invalidateQueries({ queryKey: ["results"] });
    } catch (e) {
      setError(e);
      await client.invalidateQueries({ queryKey: ["result", id] });
    } finally {
      setBusy(false);
    }
  }
  if (query.isPending) return <Loading />;
  if (query.isError) return <ErrorNotice error={query.error} />;
  const r = query.data;
  const canReview = ["admin", "reviewer"].includes(user?.role ?? "");
  const claimed =
    !!r.review_owner &&
    [user?.id, user?.username].includes(r.review_owner) &&
    !!r.review_expires_at &&
    Date.parse(r.review_expires_at) > Date.now();
  const candidates = r.candidates ?? [];
  return (
    <>
      <Link className="back-link" to={`/runs/${r.run_id}`}>
        <ArrowLeft size={16} aria-hidden="true" />
        Volver al procesamiento
      </Link>
      <PageHeader
        eyebrow={`UBICACIÓN · REVISIÓN ${r.revision}`}
        title={r.complaint_id || "Ubicación sin identificador"}
        description={`${r.source_row_count ?? 0} filas de origen vinculadas · UBIGEO ${r.ubigeo || "no disponible"}`}
        actions={<Badge value={r.resolution} />}
      />
      <div className="detail-grid">
        <div className="stack">
          <section className="panel form-panel">
            <div className="panel-heading">
              <h2>Dirección y resolución</h2>
              <MapPin size={21} className="teal" aria-hidden="true" />
            </div>
            <dl className="address-compare">
              <div>
                <dt>REGISTRO ORIGINAL</dt>
                <dd>{r.location_original || "Sin dirección"}</dd>
              </div>
              <div>
                <dt>DIRECCIÓN NORMALIZADA</dt>
                <dd>{r.location_normalized || "Sin dirección normalizada"}</dd>
              </div>
            </dl>
            <div className="detail-metrics">
              <div>
                <span>Método</span>
                <strong>{label(r.method)}</strong>
              </div>
              <div>
                <span>Precisión</span>
                <strong>{label(r.precision)}</strong>
              </div>
              <div>
                <span>Evidencia</span>
                <strong>{label(r.evidence_band)}</strong>
              </div>
              <div>
                <span>Producto</span>
                <strong>{label(r.product)}</strong>
              </div>
            </div>
            <p className="reason">{r.reason}</p>
            <div className="coordinate-row">
              <span>
                Latitud <strong>{r.latitude ?? "—"}</strong>
              </span>
              <span>
                Longitud <strong>{r.longitude ?? "—"}</strong>
              </span>
            </div>
          </section>
          <section className="panel form-panel">
            <div className="panel-heading">
              <h2>Candidatos encontrados</h2>
              <span className="count-chip">{candidates.length}</span>
            </div>
            {candidates.length ? (
              <div className="candidate-list">
                {candidates.map((c) => (
                  <article
                    key={c.id}
                    className={`candidate ${candidate === c.id ? "selected" : ""}`}
                  >
                    <div>
                      <strong>{c.label}</strong>
                      <p>
                        {label(c.method)} · Precisión: {label(c.precision)}
                      </p>
                      <small className="mono">
                        {c.latitude}, {c.longitude}
                      </small>
                    </div>
                    <div className="candidate-score">
                      Puntaje técnico<strong>{c.score}</strong>
                      <small>No es probabilidad</small>
                    </div>
                    <ul className="evidence-list">
                      {c.evidence.map((e, i) => (
                        <li key={i}>{displayValue(e)}</li>
                      ))}
                    </ul>
                    {canReview && (
                      <button
                        type="button"
                        className="button secondary"
                        onClick={() => {
                          setCandidate(c.id);
                          setAction("accept_candidate");
                        }}
                      >
                        {candidate === c.id ? (
                          <>
                            <Check size={16} aria-hidden="true" />
                            Seleccionado
                          </>
                        ) : (
                          "Seleccionar candidato"
                        )}
                      </button>
                    )}
                  </article>
                ))}
              </div>
            ) : (
              <Empty
                title="Sin candidatos disponibles"
                text="Consulta los intentos de búsqueda y la razón de resolución antes de decidir."
              />
            )}
          </section>
          <section className="panel form-panel">
            <div className="panel-heading">
              <h2>Transformaciones e intentos</h2>
            </div>
            <details>
              <summary>Ver campos normalizados</summary>
              <dl className="key-values">
                {Object.entries(r.normalized ?? {})
                  .filter(([key]) => !["legacy", "raw"].includes(key))
                  .map(([key, value]) => (
                    <div key={key}>
                      <dt>{label(key)}</dt>
                      <dd>{displayValue(value)}</dd>
                    </div>
                  ))}
              </dl>
            </details>
            <details>
              <summary>
                Transformaciones ({r.transformations?.length ?? 0})
              </summary>
              <pre>{JSON.stringify(r.transformations ?? [], null, 2)}</pre>
            </details>
            <details>
              <summary>
                Intentos de resolución ({r.attempts?.length ?? 0})
              </summary>
              <pre>{JSON.stringify(r.attempts ?? [], null, 2)}</pre>
            </details>
          </section>
        </div>
        <div className="stack">
          <section className="panel map-panel">
            <Suspense fallback={<Loading text="Preparando visor espacial…" />}>
              <LocationMap
                latitude={r.latitude}
                longitude={r.longitude}
                candidates={candidates}
              />
            </Suspense>
          </section>
          <section className="panel form-panel decision-panel">
            <div className="panel-heading">
              <div>
                <h2>Decisión de revisión</h2>
                <p>Documenta la evidencia que respalda el resultado.</p>
              </div>
              <ClipboardCheck size={23} className="teal" aria-hidden="true" />
            </div>
            <ErrorNotice error={error} />
            {success && <Success>{success}</Success>}
            {!canReview ? (
              <Notice>
                Tu rol permite consultar esta ubicación. La decisión requiere un
                revisor o administrador.
              </Notice>
            ) : (
              <>
                {!claimed ? (
                  <>
                    <Notice>
                      {r.review_owner
                        ? `Esta ubicación está asignada a ${r.review_owner}. Vigencia: ${date(r.review_expires_at)}.`
                        : "Toma la ubicación para reservarla durante la revisión."}
                    </Notice>
                    <button
                      className="button primary full"
                      onClick={() => void claim()}
                      disabled={busy}
                    >
                      <LockKeyhole size={16} aria-hidden="true" />
                      Tomar revisión
                    </button>
                  </>
                ) : (
                  <form className="decision-form" onSubmit={submit}>
                    <div className="claimed">
                      Asignada a ti · hasta {date(r.review_expires_at)}
                    </div>
                    <label>
                      Acción
                      <select
                        aria-label="Acción"
                        value={action}
                        onChange={(e) => setAction(e.target.value)}
                      >
                        <option value="accept_candidate">
                          Aceptar un candidato
                        </option>
                        <option value="manual_point">
                          Registrar punto con evidencia
                        </option>
                        <option value="address_only">
                          Conservar dirección sin punto
                        </option>
                        <option value="unresolved">
                          Mantener sin resolver
                        </option>
                        <option value="reopen">Reabrir revisión</option>
                      </select>
                    </label>
                    {action === "accept_candidate" && (
                      <label>
                        Candidato
                        <select
                          aria-label="Candidato"
                          required
                          value={candidate}
                          onChange={(e) => setCandidate(e.target.value)}
                        >
                          <option value="">Seleccionar candidato</option>
                          {candidates.map((c) => (
                            <option key={c.id} value={c.id}>
                              {c.label}
                            </option>
                          ))}
                        </select>
                        {!candidates.length && (
                          <span className="field-hint">
                            No hay candidatos; elige otra acción.
                          </span>
                        )}
                      </label>
                    )}
                    {action === "manual_point" && (
                      <>
                        <div className="form-grid">
                          <label>
                            Latitud
                            <input
                              required
                              type="number"
                              step="any"
                              min="-90"
                              max="90"
                              value={latitude}
                              onChange={(e) => setLatitude(e.target.value)}
                              placeholder="-12.0464"
                            />
                          </label>
                          <label>
                            Longitud
                            <input
                              required
                              type="number"
                              step="any"
                              min="-180"
                              max="180"
                              value={longitude}
                              onChange={(e) => setLongitude(e.target.value)}
                              placeholder="-77.0428"
                            />
                          </label>
                        </div>
                        <label>
                          Precisión espacial
                          <select
                            aria-label="Precisión espacial"
                            value={precision}
                            onChange={(e) => setPrecision(e.target.value)}
                          >
                            {precisions.map((p) => (
                              <option key={p} value={p}>
                                {label(p)}
                              </option>
                            ))}
                          </select>
                        </label>
                        <label>
                          Evidencia del punto
                          <textarea
                            required
                            minLength={8}
                            value={evidence}
                            onChange={(e) => setEvidence(e.target.value)}
                            placeholder="Fuente, versión, referencia consultada y verificación territorial"
                          />
                        </label>
                      </>
                    )}
                    {action === "address_only" && (
                      <label>
                        Dirección documentada
                        <input
                          required
                          value={address}
                          onChange={(e) => setAddress(e.target.value)}
                        />
                      </label>
                    )}
                    <label>
                      Motivo de la decisión
                      <textarea
                        required
                        minLength={8}
                        value={reason}
                        onChange={(e) => setReason(e.target.value)}
                        placeholder="Explica qué verificaste y por qué corresponde esta decisión."
                      />
                    </label>
                    <button
                      className="button primary full"
                      disabled={
                        busy || (action === "accept_candidate" && !candidate)
                      }
                    >
                      {busy ? "Guardando…" : "Registrar decisión"}
                    </button>
                    <small className="field-hint">
                      Se conservará una nueva revisión. Los conflictos de
                      edición se validan antes de guardar.
                    </small>
                  </form>
                )}
              </>
            )}
          </section>
        </div>
      </div>
      <section className="panel form-panel history-panel">
        <div className="panel-heading">
          <h2>Historial de decisiones</h2>
          <History size={21} className="muted" aria-hidden="true" />
        </div>
        {r.history?.length ? (
          <ol className="timeline">
            {r.history.map((h, i) => (
              <li key={i}>
                <span className="timeline-dot" />
                <div>
                  <strong>
                    {label(String(h.action ?? "decisión"))} · Revisión{" "}
                    {String(h.revision ?? "—")}
                  </strong>
                  <p>{String(h.reason ?? "")}</p>
                  <small>
                    {String(h.actor ?? "Sistema")} ·{" "}
                    {date(String(h.created_at ?? ""))}
                  </small>
                  <details>
                    <summary>Ver instantánea de revisión</summary>
                    <pre>{JSON.stringify(h.snapshot ?? {}, null, 2)}</pre>
                  </details>
                </div>
              </li>
            ))}
          </ol>
        ) : (
          <p className="muted">
            Todavía no hay decisiones manuales registradas.
          </p>
        )}
      </section>
    </>
  );
}
