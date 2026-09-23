import { lazy, Suspense, useEffect, useState, type FormEvent } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  useLocation,
  useNavigate,
  useParams,
  useSearchParams,
} from "react-router-dom";
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
import {
  qualityFlagLabel,
  qualityStageLabel,
  reviewStateLabel,
} from "../lib/quality";
import {
  canReuseCandidate,
  geometryLabel,
  isAreaGeometry,
  isAreaPrecision,
  pointPrecisions,
} from "../lib/geometry";
import {
  nextReviewParams,
  reservationIsLive,
  reviewBuckets,
  reviewReason,
  validReviewReturn,
} from "../lib/review";
import type { LocationResult } from "../types";
import { EquivalentReview } from "../components/EquivalentReview";
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
  "COORDENADA",
  "DESCONOCIDA",
];
export function ResultDetail() {
  const { id } = useParams();
  return <ResultRecord key={id} />;
}
function ResultRecord() {
  const { id } = useParams();
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const location = useLocation();
  const { user } = useAuth();
  const client = useQueryClient();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>();
  const [success, setSuccess] = useState(location.state?.reviewNotice ?? "");
  const [nextEmpty, setNextEmpty] = useState(false);
  const [clock, setClock] = useState(Date.now());
  const [action, setAction] = useState("accept_candidate");
  const [candidate, setCandidate] = useState("");
  const [latitude, setLatitude] = useState("");
  const [longitude, setLongitude] = useState("");
  const [precision, setPrecision] = useState("COORDENADA");
  const [address, setAddress] = useState("");
  const [reason, setReason] = useState("");
  const [evidence, setEvidence] = useState("");
  const [learnAddress, setLearnAddress] = useState(false);
  const [revokedMemory, setRevokedMemory] = useState<string[]>([]);
  const query = useQuery({
    queryKey: ["result", id],
    queryFn: () => request<LocationResult>(`/results/${id}`),
  });
  const mayLearn =
    !!query.data?.ubigeo &&
    !!query.data.location_normalized &&
    ((action === "accept_candidate" &&
      canReuseCandidate(
        query.data.candidates?.find((item) => item.id === candidate),
      )) ||
      (action === "manual_point" && pointPrecisions.includes(precision)));
  useEffect(() => setLearnAddress(false), [action, candidate, precision]);
  useEffect(() => {
    const timer = setInterval(() => setClock(Date.now()), 15000);
    return () => clearInterval(timer);
  }, []);
  useEffect(() => {
    if (!query.data) return;
    setAddress(
      query.data.location_normalized || query.data.location_original || "",
    );
    setAction(
      query.data.review_status === "CLOSED"
        ? "reopen"
        : query.data.candidates?.length
          ? "accept_candidate"
          : query.data.location_normalized
            ? "address_only"
            : "unresolved",
    );
  }, [query.data?.id]);
  const back = validReviewReturn(
    searchParams.get("back"),
    query.data?.run_id ?? "",
  );
  async function invalidate() {
    await Promise.all(
      [
        "result",
        "results",
        "review-queue",
        "review-summary",
        "dashboard",
        "run",
        "runs",
        "run-readiness",
        "quality",
      ].map((key) => client.invalidateQueries({ queryKey: [key] })),
    );
  }
  async function release(destination?: string) {
    setBusy(true);
    setError(null);
    try {
      if (query.data?.review_owner === user?.id)
        await post(`/results/${id}/release`);
      await invalidate();
      if (destination) navigate(destination);
    } catch (error) {
      setError(error);
    } finally {
      setBusy(false);
    }
  }
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
  async function revokeMemory(memoryId: string) {
    setBusy(true);
    setError(null);
    setSuccess("");
    try {
      await post(`/address-memory/${encodeURIComponent(memoryId)}/revoke`, {
        reason: "Desactivación solicitada desde la ficha de ubicación",
      });
      setRevokedMemory((previous) => [...previous, memoryId]);
      setSuccess(
        "Reutilización desactivada. Los resultados y las decisiones históricas se conservan.",
      );
      await invalidate();
    } catch (error) {
      setError(error);
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
    setNextEmpty(false);
    const openNext =
      (event.nativeEvent as SubmitEvent).submitter?.getAttribute("value") ===
      "next";
    let saved = false;
    try {
      const payload: Record<string, unknown> = {
        expected_revision: query.data.revision,
        action,
        reason,
        learn_address: mayLearn && learnAddress,
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
      saved = true;
      setSuccess(
        "Decisión registrada. La revisión anterior se conserva en el historial.",
      );
      setReason("");
      setLearnAddress(false);
      setEvidence("");
      setCandidate("");
      setLatitude("");
      setLongitude("");
      setPrecision("COORDENADA");
      setAction(
        action === "reopen"
          ? query.data.candidates?.length
            ? "accept_candidate"
            : query.data.location_normalized
              ? "address_only"
              : "unresolved"
          : "reopen",
      );
      await invalidate();
      if (openNext) {
        const next = await request<{ item: LocationResult | null }>(
          `/review/next?${nextReviewParams(back, query.data.run_id, id!)}`,
        );
        if (next.item)
          navigate(
            `/results/${next.item.id}?back=${encodeURIComponent(back)}`,
            {
              state: {
                reviewNotice:
                  "Decisión anterior registrada. Examina este registro antes de tomar su revisión.",
              },
            },
          );
        else setNextEmpty(true);
      }
    } catch (e) {
      setError(
        saved
          ? new Error(
              `La decisión se guardó, pero no se pudo abrir el siguiente registro. ${e instanceof Error ? e.message : "Vuelve a la bandeja para continuar."}`,
            )
          : e,
      );
      await client.invalidateQueries({ queryKey: ["result", id] });
    } finally {
      setBusy(false);
    }
  }
  if (query.isPending) return <Loading />;
  if (query.isError) return <ErrorNotice error={query.error} />;
  const r = query.data;
  const canReview = ["admin", "reviewer"].includes(user?.role ?? "");
  const canManage = ["admin", "operator"].includes(user?.role ?? "");
  const claimed =
    !!r.review_owner &&
    [user?.id, user?.username].includes(r.review_owner) &&
    reservationIsLive(r.review_expires_at, clock);
  const candidates = r.candidates ?? [];
  const memoryReferences = new Map<string, string>();
  const ownMemory = r.normalized?.learned_reference_id;
  if (typeof ownMemory === "string" && ownMemory)
    memoryReferences.set(ownMemory, "Validación registrada desde esta ficha");
  candidates.forEach((item, index) => {
    if (
      item.id.startsWith("memory:") &&
      !memoryReferences.has(item.id.slice(7))
    )
      memoryReferences.set(
        item.id.slice(7),
        `Candidato ${index + 1} · ${item.label}`,
      );
  });
  const reservedByOther =
    !!r.review_owner &&
    r.review_owner !== user?.id &&
    reservationIsLive(r.review_expires_at, clock);
  const blocked = ["needs_reference", "technical"].includes(r.review_bucket);
  return (
    <>
      <button
        className="back-link plain-button"
        disabled={busy}
        onClick={() => void release(back)}
      >
        <ArrowLeft size={16} aria-hidden="true" />
        {claimed
          ? "Volver y liberar reserva"
          : back.startsWith("/review")
            ? "Volver a la bandeja"
            : "Volver al procesamiento"}
      </button>
      <PageHeader
        eyebrow={`UBICACIÓN · REVISIÓN ${r.revision}`}
        title={r.complaint_id || "Ubicación sin identificador"}
        description={`${r.source_row_count ?? 0} filas de origen vinculadas · UBIGEO ${r.ubigeo || "no disponible"}`}
        actions={<Badge value={r.resolution} />}
      />
      <div className="record-context">
        {r.review_state && <span>{reviewStateLabel(r.review_state)}</span>}
        {r.quality_stage && (
          <span>
            {qualityFlagLabel(r.quality_flag)} ·{" "}
            {qualityStageLabel(r.quality_stage)}
          </span>
        )}
        <span
          className={`review-stage ${r.review_status === "CLOSED" ? "closed" : ""}`}
        >
          {r.review_status === "CLOSED" ? "Finalizado" : "Pendiente"}
        </span>
        {r.review_bucket !== "none" && (
          <span>{reviewBuckets[r.review_bucket]?.label}</span>
        )}
        <button
          className="text-link plain-button"
          disabled={busy}
          onClick={() =>
            void release(`/review?run_id=${r.run_id}&bucket=all&stage=open`)
          }
        >
          Ver pendientes de esta ejecución
        </button>
      </div>
      {r.review_state === "quick_review" && r.review_status === "OPEN" && (
        <Notice>
          Revisión rápida de puerta: verifica el nombre de vía sugerido, el
          número de puerta y el distrito. Registra el candidato respaldado por
          la evidencia para finalizar este caso y continuar con el siguiente.
        </Notice>
      )}
      {r.review_bucket === "needs_reference" && (
        <Notice>
          Falta una referencia evaluable. La vía principal es incorporar una
          fuente documentada y crear un nuevo procesamiento con ella; revisar
          uno por uno no reemplaza ese catálogo.
          <div className="button-row">
            <button
              className="text-link plain-button"
              onClick={() => void release("/references")}
              disabled={busy}
            >
              Ver catálogos
            </button>
            {canManage ? (
              <button
                className="text-link plain-button"
                onClick={() => void release(`/runs/${r.run_id}?tab=reprocess`)}
                disabled={busy}
              >
                Preparar nuevo procesamiento
              </button>
            ) : (
              <span>
                Solicita a un operador que prepare el nuevo procesamiento.
              </span>
            )}
          </div>
        </Notice>
      )}
      {r.review_bucket === "needs_data" && (
        <Notice>
          Esta ubicación necesita información adicional de la fuente. Conservar
          la dirección o cerrar sin punto exige una conclusión documentada; no
          se completan coordenadas por suposición.
        </Notice>
      )}
      {r.review_bucket === "technical" && (
        <Notice>
          Hay una limitación técnica del procesamiento. Consulta la ejecución y
          su configuración antes de adoptar una decisión espacial.
        </Notice>
      )}
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
            <p className="reason">{reviewReason(r.reason)}</p>
            {r.method === "COORD_ORIGINAL" && (
              <Notice>
                <strong>
                  {r.resolution === "ACEPTADO_AUTOMATICO"
                    ? "Coordenada original validada territorialmente."
                    : "Coordenada original declarada, pendiente de corroboración."}
                </strong>{" "}
                La pertenencia al distrito no demuestra una coincidencia con la
                puerta o dirección del hecho.
              </Notice>
            )}
            {r.precision === "PUERTA" && r.product === "PUNTO" && (
              <Notice>
                <strong>Ubicación a nivel de puerta.</strong> La evidencia y el
                método indican cómo se corroboró la dirección con su referencia.
              </Notice>
            )}
            {r.method === "DIRECCION_VALIDADA" && (
              <Notice>
                Resultado procedente de una dirección validada previamente.
                Conserva la precisión y la referencia de la revisión de origen
                para una coincidencia de dirección normalizada y UBIGEO.
              </Notice>
            )}
            {r.product === "AREA_TRAMO" || isAreaGeometry(r.geometry) ? (
              <Notice>
                <strong>{geometryLabel(r.geometry)}.</strong> La ubicación se
                representa mediante su geometría de referencia, sin asignar un
                punto exacto.
              </Notice>
            ) : (
              <div className="coordinate-row">
                <span>
                  Latitud <strong>{r.latitude ?? "—"}</strong>
                </span>
                <span>
                  Longitud <strong>{r.longitude ?? "—"}</strong>
                </span>
              </div>
            )}
            {r.geometry && (
              <details>
                <summary>Ver geometría GeoJSON de la ubicación</summary>
                <pre>{JSON.stringify(r.geometry, null, 2)}</pre>
              </details>
            )}
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
                      {isAreaPrecision(c.precision) ||
                      isAreaGeometry(c.geometry) ? (
                        <small>
                          {geometryLabel(c.geometry)} · No representa un punto
                          exacto.
                        </small>
                      ) : (
                        <small className="mono">
                          {c.latitude ?? "—"}, {c.longitude ?? "—"}
                        </small>
                      )}
                      {c.method === "DIRECCION_VALIDADA" && (
                        <p className="field-hint">
                          Referencia de una revisión previa; consulta su
                          evidencia de origen.
                        </p>
                      )}
                    </div>
                    <div className="candidate-score">
                      Puntaje técnico<strong>{c.score ?? "No aplica"}</strong>
                      <small>No es probabilidad</small>
                    </div>
                    <ul
                      className="evidence-list"
                      aria-label="Evidencia del candidato"
                    >
                      {c.evidence.map((e, i) => (
                        <li key={i}>
                          {typeof e === "string"
                            ? reviewReason(e)
                            : displayValue(e)}
                        </li>
                      ))}
                    </ul>
                    {canReview && (
                      <button
                        type="button"
                        className="button secondary"
                        disabled={
                          r.review_status === "CLOSED" || reservedByOther
                        }
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
            {canReview && memoryReferences.size > 0 && (
              <div className="memory-management">
                <h3>Reutilización de direcciones</h3>
                <p className="field-hint">
                  Desactiva una referencia para que deje de resolver futuros
                  lotes. Los resultados históricos conservan su evidencia.
                </p>
                {Array.from(memoryReferences, ([memoryId, description]) => (
                  <div className="memory-entry" key={memoryId}>
                    <span>{description}</span>
                    {revokedMemory.includes(memoryId) ? (
                      <strong className="teal">
                        Reutilización desactivada
                      </strong>
                    ) : (
                      <button
                        className="button secondary"
                        type="button"
                        disabled={busy}
                        onClick={() => void revokeMemory(memoryId)}
                      >
                        Desactivar reutilización
                      </button>
                    )}
                  </div>
                ))}
              </div>
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
          {canReview &&
            r.review_status === "OPEN" &&
            r.review_bucket === "actionable" && (
              <EquivalentReview
                key={`${r.id}:${r.revision}`}
                resultId={r.id}
                onSaved={async (message) => {
                  setSuccess(message);
                  await invalidate();
                }}
              />
            )}
          <section className="panel map-panel">
            <Suspense fallback={<Loading text="Preparando visor espacial…" />}>
              <LocationMap
                latitude={r.latitude}
                longitude={r.longitude}
                candidates={candidates}
                selectedCandidateId={candidate}
                geometry={r.geometry}
                precision={r.precision}
                runId={r.run_id}
                ubigeo={r.ubigeo}
                resultMethod={r.method}
                coordinateWarnings={
                  Array.isArray(r.normalized?.warnings)
                    ? r.normalized.warnings
                    : []
                }
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
            {nextEmpty && (
              <Notice>
                No quedan pendientes disponibles con estos filtros. Puedes
                volver a la bandeja para consultar reservas vigentes, otros
                motivos o los finalizados.
              </Notice>
            )}
            {!canReview ? (
              <Notice>
                Tu rol permite consultar esta ubicación. La decisión requiere un
                revisor o administrador.
              </Notice>
            ) : (
              <details
                className="review-decision-disclosure"
                open={!blocked || claimed}
              >
                <summary>
                  {blocked
                    ? "Decisión manual excepcional"
                    : "Registrar una decisión"}
                </summary>
                {!claimed ? (
                  <>
                    <Notice>
                      {r.review_owner
                        ? `Esta ubicación tiene una reserva ${reservedByOther ? "de otro revisor" : "vencida"}. Vigencia: ${date(r.review_expires_at)}.`
                        : "Toma la ubicación para reservarla durante la revisión."}
                    </Notice>
                    <button
                      className="button primary full"
                      onClick={() => void claim()}
                      disabled={busy || reservedByOther}
                    >
                      <LockKeyhole size={16} aria-hidden="true" />
                      {reservedByOther
                        ? "Reservada por otro revisor"
                        : "Tomar revisión"}
                    </button>
                  </>
                ) : (
                  <form className="decision-form" onSubmit={submit}>
                    <div className="claimed">
                      Asignada a ti · hasta {date(r.review_expires_at)}
                      <button
                        type="button"
                        className="plain-button inline-link"
                        disabled={busy}
                        onClick={() => void release()}
                      >
                        Liberar reserva
                      </button>
                    </div>
                    <label>
                      Acción
                      <select
                        aria-label="Acción"
                        value={action}
                        onChange={(e) => setAction(e.target.value)}
                      >
                        <option
                          value="accept_candidate"
                          disabled={
                            !candidates.length || r.review_status === "CLOSED"
                          }
                        >
                          Aceptar un candidato
                        </option>
                        <option
                          value="manual_point"
                          disabled={r.review_status === "CLOSED"}
                        >
                          Registrar punto con evidencia
                        </option>
                        <option
                          value="address_only"
                          disabled={r.review_status === "CLOSED"}
                        >
                          Conservar dirección sin punto
                        </option>
                        <option
                          value="unresolved"
                          disabled={r.review_status === "CLOSED"}
                        >
                          Finalizar sin punto resuelto
                        </option>
                        <option
                          value="reopen"
                          disabled={r.review_status !== "CLOSED"}
                        >
                          Reabrir revisión
                        </option>
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
                    {mayLearn && (
                      <div className="reuse-address">
                        <label className="checkbox-label">
                          <input
                            type="checkbox"
                            checked={learnAddress}
                            onChange={(event) =>
                              setLearnAddress(event.target.checked)
                            }
                            disabled={busy}
                          />
                          Reutilizar esta dirección validada en futuros lotes
                        </label>
                        <p className="field-hint">
                          Se conservará una referencia para la misma dirección
                          normalizada y UBIGEO, con esta precisión y revisión de
                          origen. La opción se aplica únicamente a esta
                          decisión.
                        </p>
                      </div>
                    )}
                    <button
                      className="button primary full"
                      type="submit"
                      value="save"
                      disabled={
                        busy || (action === "accept_candidate" && !candidate)
                      }
                    >
                      {busy ? "Guardando…" : "Registrar decisión"}
                    </button>
                    {r.review_status === "OPEN" && (
                      <button
                        className="button secondary full"
                        type="submit"
                        value="next"
                        disabled={
                          busy || (action === "accept_candidate" && !candidate)
                        }
                      >
                        Guardar y siguiente
                      </button>
                    )}
                    <small className="field-hint">
                      Se conservará una nueva revisión. Los conflictos de
                      edición se validan antes de guardar.
                    </small>
                  </form>
                )}
              </details>
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
