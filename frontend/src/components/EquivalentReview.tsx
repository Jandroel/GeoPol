import { useState, type FormEvent } from "react";
import { ApiError, post, request } from "../lib/api";
import { label, number } from "../lib/format";
import { reviewReason } from "../lib/review";
import type { LocationResult, ReviewGroupPreview } from "../types";
import { ErrorNotice, Notice } from "./ui";

export function EquivalentReview({
  resultId,
  onSaved,
}: {
  resultId: string;
  onSaved: (message: string) => Promise<void>;
}) {
  const [preview, setPreview] = useState<ReviewGroupPreview | null>(null);
  const [candidate, setCandidate] = useState("");
  const [reason, setReason] = useState("");
  const [confirmed, setConfirmed] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>();
  const [stale, setStale] = useState(false);
  async function load() {
    setBusy(true);
    setError(null);
    setConfirmed(false);
    setCandidate("");
    setPreview(null);
    try {
      setPreview(
        await request<ReviewGroupPreview>(
          `/results/${resultId}/review-group/preview`,
        ),
      );
      setStale(false);
    } catch (error) {
      setError(error);
    } finally {
      setBusy(false);
    }
  }
  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!preview?.token || !confirmed || !candidate || stale) return;
    setBusy(true);
    setError(null);
    try {
      const response = await post<{
        applied_count: number;
        item: LocationResult;
      }>(`/results/${resultId}/review-group/decide`, {
        token: preview.token,
        candidate_id: candidate,
        reason: reason.trim(),
      });
      setPreview(null);
      setConfirmed(false);
      setReason("");
      await onSaved(
        `Decisión registrada en ${number(response.applied_count)} ubicaciones equivalentes. Cada una conserva su revisión e historial.`,
      );
    } catch (error) {
      setError(
        error instanceof ApiError && error.status === 409
          ? new Error(
              `${error.message} Actualiza la vista previa y vuelve a comprobar el alcance.`,
            )
          : error,
      );
      // A failed/uncertain write must never replay an old group token.
      setStale(true);
      setConfirmed(false);
    } finally {
      setBusy(false);
    }
  }
  const applicable =
    preview?.eligible &&
    preview.count >= 2 &&
    !preview.truncated &&
    !!preview.token;
  return (
    <section
      className="panel form-panel equivalent-review"
      aria-label="Revisión de ubicaciones equivalentes"
    >
      <h2>Revisar ubicaciones equivalentes</h2>
      <p>
        Una decisión documentada puede cubrir direcciones equivalentes de esta
        ejecución, con los mismos candidatos y controles compatibles.
      </p>
      <button
        type="button"
        className="button secondary"
        disabled={busy}
        onClick={() => void load()}
      >
        {busy
          ? "Comprobando…"
          : preview || stale
            ? "Actualizar vista previa"
            : "Buscar equivalentes"}
      </button>
      <ErrorNotice error={error} />
      {preview && (
        <>
          <p role="status">
            <strong>
              {number(preview.count)} ubicaciones ·{" "}
              {number(preview.source_rows)} filas de origen
            </strong>
            . El alcance incluye esta ficha.
          </p>
          {!applicable && (
            <Notice>
              {preview.reason
                ? reviewReason(preview.reason)
                : preview.truncated
                  ? `El grupo supera el límite de ${preview.limit} ubicaciones. No se permite aplicar una selección incompleta.`
                  : "No hay al menos dos ubicaciones elegibles para una decisión conjunta."}
            </Notice>
          )}
          {preview.excluded_count > 0 && (
            <Notice>
              {number(preview.excluded_count)} ubicaciones excluidas por
              diferencias de evidencia, estado o reservas.
            </Notice>
          )}
          {!!preview.members.length && (
            <details open>
              <summary>
                Ubicaciones incluidas ({number(preview.members.length)})
              </summary>
              <div className="table-scroll group-preview-table">
                <table>
                  <thead>
                    <tr>
                      <th>Denuncia</th>
                      <th>Dirección</th>
                      <th>UBIGEO</th>
                      <th>Revisión</th>
                    </tr>
                  </thead>
                  <tbody>
                    {preview.members.map((member) => (
                      <tr key={member.id}>
                        <td>{member.complaint_id || "Sin identificador"}</td>
                        <td>{member.location_normalized}</td>
                        <td>{member.ubigeo}</td>
                        <td>{member.revision}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </details>
          )}
          {applicable && (
            <form className="decision-form" onSubmit={submit}>
              <label>
                Candidato para el grupo
                <select
                  required
                  aria-label="Candidato para el grupo"
                  value={candidate}
                  disabled={busy || stale}
                  onChange={(event) => {
                    setCandidate(event.target.value);
                    setConfirmed(false);
                  }}
                >
                  <option value="">Seleccionar candidato común</option>
                  {preview.candidates.map((item) => (
                    <option key={item.id} value={item.id}>
                      {item.label} · {label(item.precision)} ·{" "}
                      {item.source || "Fuente no declarada"}
                      {item.version ? ` · ${item.version}` : ""}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                Motivo de la decisión conjunta
                <textarea
                  required
                  minLength={8}
                  maxLength={2000}
                  value={reason}
                  disabled={busy || stale}
                  onChange={(event) => setReason(event.target.value)}
                />
              </label>
              <label className="checkbox-label">
                <input
                  type="checkbox"
                  checked={confirmed}
                  disabled={busy || stale}
                  onChange={(event) => setConfirmed(event.target.checked)}
                />
                He revisado el candidato y las {number(preview.count)}{" "}
                ubicaciones incluidas; la misma evidencia respalda esta
                decisión.
              </label>
              <p className="field-hint">
                Solo acepta el candidato seleccionado. No agrega puntos manuales
                ni activa la reutilización en futuros lotes. Si cambia una
                revisión o reserva, habrá que actualizar esta vista previa.
              </p>
              <button
                className="button primary full"
                disabled={
                  busy ||
                  stale ||
                  !confirmed ||
                  !candidate ||
                  reason.trim().length < 8
                }
              >
                Aplicar decisión a {number(preview.count)} ubicaciones
              </button>
            </form>
          )}
        </>
      )}
    </section>
  );
}
