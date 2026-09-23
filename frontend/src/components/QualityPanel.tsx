import { useEffect, useState, type CSSProperties } from "react";
import { Link } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowRight, ListFilter } from "lucide-react";
import { useAuth } from "../auth";
import { post, request } from "../lib/api";
import { isActiveRun, number } from "../lib/format";
import {
  percentage,
  qualityFlagLabel,
  qualityStageLabel,
  reviewStateLabels,
  reviewStateLabel,
} from "../lib/quality";
import type { QualityOverview, Run } from "../types";
import { Empty, ErrorNotice, Loading, Notice } from "./ui";
import { ExportPanel } from "./ExportPanel";
import { ResultsTable } from "./ResultsTable";

const chartCategories = [
  { key: "resolved", label: "Resueltos", color: "var(--success)" },
  { key: "review", label: "Por revisar", color: "var(--amber)" },
  { key: "unmatched", label: "Sin coincidencia", color: "var(--accent)" },
  {
    key: "blocked",
    label: "Referencia o datos pendientes",
    color: "var(--slate)",
  },
] as const;
function StageChart({ stage }: { stage: QualityOverview["stages"][number] }) {
  let previous = 0;
  const gradient = chartCategories
    .map(({ key, color }) => {
      const start = previous;
      previous += stage.units ? (stage[key] / stage.units) * 100 : 0;
      return `${color} ${start}% ${previous}%`;
    })
    .join(", ");
  return (
    <div className="quality-chart-content">
      <div
        className="quality-donut"
        aria-hidden="true"
        style={
          {
            background: stage.units
              ? `conic-gradient(${gradient})`
              : "var(--border)",
          } as CSSProperties
        }
      >
        <span>
          <strong>{number(stage.units)}</strong>
          <small>ubicaciones</small>
        </span>
      </div>
      <table className="quality-legend">
        <caption className="sr-only">
          Distribución de {stage.label}. Porcentajes sobre {stage.units}{" "}
          ubicaciones evaluadas en esta etapa.
        </caption>
        <thead className="sr-only">
          <tr>
            <th>Estado</th>
            <th>Cantidad</th>
            <th>Porcentaje</th>
          </tr>
        </thead>
        <tbody>
          {chartCategories.map(({ key, label, color }) => (
            <tr key={key}>
              <th scope="row">
                <span
                  className="legend-swatch"
                  style={{ background: color }}
                  aria-hidden="true"
                />
                {label}
              </th>
              <td>{number(stage[key])}</td>
              <td>{percentage(stage[key], stage.units)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
export function QualityPanel({ run }: { run: Run }) {
  const { user } = useAuth();
  const client = useQueryClient();
  const [selectedFlag, setSelectedFlag] = useState("");
  const [selectedStage, setSelectedStage] = useState("");
  const [selectedReviewState, setSelectedReviewState] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>();
  const active = isActiveRun(run.status);
  const canManage = ["admin", "operator"].includes(user?.role ?? "");
  const isQuality = run.config.workflow === "quality_v1";
  const summary = useQuery({
    queryKey: ["quality", run.id, run.status, run.processed_units],
    queryFn: () => request<QualityOverview>(`/runs/${run.id}/quality`),
    enabled: isQuality,
    refetchInterval: active ? 2500 : 15000,
  });
  useEffect(() => {
    if (!summary.dataUpdatedAt) return;
    // A short stage may start and finish between run polls, leaving its status
    // and processed-unit count unchanged. Refresh rows after each confirmed
    // summary snapshot so the table follows the same completed stage.
    void client.invalidateQueries({ queryKey: ["results", run.id] });
  }, [client, run.id, summary.dataUpdatedAt]);
  async function advance(stage: string) {
    setBusy(true);
    setError(null);
    try {
      await post<Run>(`/runs/${run.id}/advance`, { stage });
      await Promise.all(
        ["run", "quality", "results", "runs", "review-summary"].map((key) =>
          client.invalidateQueries({ queryKey: [key] }),
        ),
      );
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  }
  if (!isQuality)
    return (
      <Empty
        title="Flags no evaluados en esta ejecución"
        text="Esta ejecución se creó con el flujo anterior. Crea un nuevo procesamiento con el flujo por calidad para consultar sus etapas sin cambiar el historial."
        action={
          canManage && (
            <Link className="button primary" to="/runs/new">
              Cargar archivos
            </Link>
          )
        }
      />
    );
  if (summary.isPending) return <Loading />;
  if (summary.isError) return <ErrorNotice error={summary.error} />;
  const data = summary.data;
  const qualityFlag = selectedFlag ? Number(selectedFlag) : undefined;
  const closedSelection = ["automatic", "accepted_manual"].includes(
    selectedReviewState,
  );
  const reviewParams = new URLSearchParams({
    run_id: run.id,
    stage: closedSelection ? "closed" : "open",
    bucket:
      closedSelection ||
      ["unmatched", "reference_pending", "unprocessed"].includes(
        selectedReviewState,
      )
        ? "all"
        : "actionable",
    ...(selectedFlag ? { quality_flag: selectedFlag } : {}),
    ...(selectedStage ? { quality_stage: selectedStage } : {}),
    ...(selectedReviewState ? { review_state: selectedReviewState } : {}),
  });
  return (
    <div className="stack quality-panel">
      <Notice>
        El flag describe la estructura de la ubicación. El estado de revisión
        informa si fue resuelta automáticamente, requiere una decisión o espera
        datos de referencia; la precisión geográfica se conserva por separado.
      </Notice>
      <section className="panel form-panel quality-progress-summary">
        <div>
          <h2>Avance por calidad</h2>
          <p>
            {number(data.totals.resolved)} de {number(data.totals.units)}{" "}
            ubicaciones resueltas (
            {percentage(data.totals.resolved, data.totals.units)}). El archivo
            original contiene {number(data.totals.source_rows)} filas.
          </p>
        </div>
        <progress
          aria-label="Ubicaciones resueltas"
          value={data.totals.resolved}
          max={Math.max(1, data.totals.units)}
        />
        <p className="field-hint">
          Los resueltos se conservan al avanzar.{" "}
          {number(data.held_review_units)} ubicaciones esperan revisión y no
          pasan automáticamente a una etapa menos precisa.
        </p>
        <ErrorNotice error={error} />
        {data.next_stage && canManage && (
          <div className="button-row">
            <button
              className="button primary"
              disabled={
                busy || active || !data.can_advance || !!run.superseded_by
              }
              onClick={() => void advance(data.next_stage!)}
            >
              {busy
                ? "Iniciando etapa…"
                : `Continuar con ${qualityStageLabel(data.next_stage).toLowerCase()}`}
              <ArrowRight size={17} aria-hidden="true" />
            </button>
            <span className="field-hint">
              {number(data.eligible_units)} ubicaciones elegibles
            </span>
          </div>
        )}
        {active && (
          <p role="status">
            Etapa en procesamiento. Los conteos se actualizan automáticamente.
          </p>
        )}
      </section>
      <p className="field-hint">
        Los gráficos resumen lo evaluado en cada etapa; los filtros y
        exportaciones muestran los resultados vigentes. Una ubicación puede
        aparecer en varios gráficos, por lo que sus cantidades no se suman.
      </p>
      <div className="quality-charts">
        {data.stages.map((stage) => (
          <section className="panel quality-stage-card" key={stage.key}>
            <div className="panel-heading">
              <div>
                <h3>{stage.label}</h3>
                <p>
                  {number(stage.source_rows)} filas vinculadas ·{" "}
                  {percentage(stage.units, data.totals.units)} del total de
                  ubicaciones
                </p>
              </div>
            </div>
            <StageChart stage={stage} />
            <button
              className="button secondary"
              onClick={() => {
                setSelectedStage(stage.key);
                setSelectedFlag("");
                setSelectedReviewState("");
              }}
            >
              <ListFilter size={16} aria-hidden="true" />
              Ver registros actuales de esta etapa
            </button>
          </section>
        ))}
      </div>
      <section className="panel form-panel">
        <div className="panel-heading">
          <div>
            <h2>Consultar y exportar un filtro</h2>
            <p>
              Cada descarga refleja el estado actual. El Excel acumulado incluye
              todas las filas, sus flags y estados de revisión actualizados.
            </p>
          </div>
        </div>
        <div className="table-scroll">
          <table className="quality-counts">
            <caption>Flag de calidad de las ubicaciones</caption>
            <thead>
              <tr>
                <th>Flag de calidad</th>
                <th>Ubicaciones</th>
                <th>% del total</th>
                <th>Filas originales</th>
              </tr>
            </thead>
            <tbody>
              {data.flags.map((quality) => (
                <tr key={quality.flag ?? "none"}>
                  <th scope="row">
                    {quality.flag == null ? (
                      "Sin flag asignado"
                    ) : (
                      <button
                        type="button"
                        className="text-link plain-button"
                        onClick={() => {
                          setSelectedFlag(String(quality.flag));
                          setSelectedStage("");
                          setSelectedReviewState("");
                        }}
                      >
                        {qualityFlagLabel(quality.flag)}
                      </button>
                    )}
                  </th>
                  <td>{number(quality.units)}</td>
                  <td>{percentage(quality.units, data.totals.units)}</td>
                  <td>{number(quality.source_rows)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <div className="table-scroll">
          <table className="quality-counts">
            <caption>Estado de revisión actual</caption>
            <thead>
              <tr>
                <th>Estado</th>
                <th>Ubicaciones</th>
                <th>% del total</th>
                <th>Filas originales</th>
              </tr>
            </thead>
            <tbody>
              {data.review_states.map((state) => (
                <tr key={state.state}>
                  <th scope="row">
                    <button
                      type="button"
                      className="text-link plain-button"
                      onClick={() => {
                        setSelectedReviewState(state.state);
                        setSelectedFlag("");
                        setSelectedStage("");
                      }}
                    >
                      {reviewStateLabel(state.state)}
                    </button>
                  </th>
                  <td>{number(state.units)}</td>
                  <td>{percentage(state.units, data.totals.units)}</td>
                  <td>{number(state.source_rows)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <div className="form-grid">
          <label>
            Flag de calidad del filtro
            <select
              value={selectedFlag}
              onChange={(e) => setSelectedFlag(e.target.value)}
            >
              <option value="">Todos los flags</option>
              {[1, 2].map((code) => {
                const value = data.flags.find((item) => item.flag === code);
                return (
                  <option key={code} value={code}>
                    {qualityFlagLabel(code)} · {number(value?.units ?? 0)}
                  </option>
                );
              })}
            </select>
          </label>
          <label>
            Estado de revisión del filtro
            <select
              value={selectedReviewState}
              onChange={(e) => setSelectedReviewState(e.target.value)}
            >
              <option value="">Todos los estados de revisión</option>
              {Object.entries(reviewStateLabels).map(([state, title]) => {
                const total = data.review_states.find(
                  (item) => item.state === state,
                );
                return (
                  <option key={state} value={state}>
                    {title} · {number(total?.units ?? 0)}
                  </option>
                );
              })}
            </select>
          </label>
          <label>
            Etapa del filtro
            <select
              value={selectedStage}
              onChange={(e) => setSelectedStage(e.target.value)}
            >
              <option value="">Todas las etapas</option>
              {data.stages.map((stage) => (
                <option key={stage.key} value={stage.key}>
                  {stage.label}
                </option>
              ))}
            </select>
          </label>
        </div>
        <div className="button-row">
          <Link className="button secondary" to={`/review?${reviewParams}`}>
            {selectedReviewState === "quick_review"
              ? "Abrir revisión rápida"
              : closedSelection
                ? "Consultar finalizados del filtro"
                : "Revisar pendientes del filtro"}
          </Link>
          {(selectedFlag || selectedStage || selectedReviewState) && (
            <button
              className="text-link plain-button"
              onClick={() => {
                setSelectedFlag("");
                setSelectedStage("");
                setSelectedReviewState("");
              }}
            >
              Ver acumulado completo
            </button>
          )}
        </div>
      </section>
      <ExportPanel
        key={`${run.id}:${selectedFlag}:${selectedStage}:${selectedReviewState}`}
        runId={run.id}
        qualityFlag={qualityFlag}
        qualityStage={selectedStage || undefined}
        reviewState={selectedReviewState || undefined}
        allowCumulative
      />
      <ResultsTable
        key={`results:${selectedFlag}:${selectedStage}:${selectedReviewState}`}
        runId={run.id}
        qualityFlag={qualityFlag}
        qualityStage={selectedStage || undefined}
        reviewState={selectedReviewState || undefined}
        live={active}
        runVersion={`${run.status}:${run.processed_units}`}
      />
    </div>
  );
}
