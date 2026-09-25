import { useEffect, useState } from "react";
import {
  AlertCircle,
  CheckCircle2,
  Clock3,
  FileSpreadsheet,
  LoaderCircle,
  PauseCircle,
} from "lucide-react";
import type { Run } from "../types";
import { isActiveRun, number } from "../lib/format";
import "./run-activity.css";

const stages: Record<string, string> = {
  door: "Puertas",
  block: "Cuadras",
  intersection: "Cruces de vías",
  street: "Vías",
  nucleus: "Núcleos y centros poblados",
  jurisdiction: "Jurisdicciones",
};

function timestamp(value: string | null | undefined) {
  if (!value) return null;
  const parsed = Date.parse(
    /(?:Z|[+-]\d\d:\d\d)$/i.test(value) ? value : `${value}Z`,
  );
  return Number.isFinite(parsed) ? parsed : null;
}

function duration(start: number | null, end: number | null) {
  if (start === null || end === null || end < start) return null;
  const seconds = Math.floor((end - start) / 1000);
  const hours = Math.floor(seconds / 3600);
  const minutes = Math.floor((seconds % 3600) / 60);
  return `${String(hours).padStart(2, "0")}:${String(minutes).padStart(2, "0")}:${String(seconds % 60).padStart(2, "0")}`;
}

/** Shows the current job, never the cumulative counter from earlier stages. */
export function RunActivity({ run }: { run: Run }) {
  const activity = run.activity;
  const active = isActiveRun(run.status);
  const queued =
    active && (activity?.phase === "queued" || run.status === "QUEUED");
  const failed = run.status === "FAILED";
  const cancelled = run.status === "CANCELLED";
  const completed = ["COMPLETED", "COMPLETED_WITH_ISSUES"].includes(run.status);
  const withIssues = run.status === "COMPLETED_WITH_ISSUES";
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    if (!active) return;
    setNow(Date.now());
    const interval = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(interval);
  }, [active, activity?.job_id]);

  // A missing job timestamp stays unknown: the original run may span many stages.
  const timer = duration(
    timestamp(queued ? activity?.queued_at : activity?.started_at),
    active ? now : timestamp(activity?.finished_at),
  );
  const stage = activity?.stage
    ? (stages[activity.stage] ?? activity.stage)
    : null;
  const ingestion =
    activity?.phase === "ingestion" || run.status === "INGESTING";
  const state = failed
    ? "failed"
    : cancelled
      ? "cancelled"
      : queued
        ? "queued"
        : active
          ? "running"
          : withIssues
            ? "issues"
            : "completed";
  const title = failed
    ? "El procesamiento necesita atención"
    : cancelled
      ? "Procesamiento cancelado"
      : queued
        ? "Archivo en cola"
        : ingestion
          ? "Leyendo el archivo Excel"
          : active
            ? "Procesamiento en curso"
            : completed
              ? stage
                ? "Etapa completada"
                : "Procesamiento completado"
              : "Estado del procesamiento";
  const status = failed
    ? "Error"
    : cancelled
      ? "Cancelado"
      : queued
        ? "En espera"
        : active
          ? "En vivo"
          : withIssues
            ? "Con incidencias"
            : completed
              ? "Finalizado"
              : "Sin actividad";
  const Icon = failed
    ? AlertCircle
    : cancelled
      ? PauseCircle
      : queued
        ? Clock3
        : active
          ? LoaderCircle
          : withIssues
            ? AlertCircle
            : CheckCircle2;
  const processed = activity?.processed_units;
  const total = activity?.total_units;
  const measurable =
    active &&
    !queued &&
    activity?.phase === "resolution" &&
    typeof processed === "number" &&
    Number.isFinite(processed) &&
    processed >= 0 &&
    typeof total === "number" &&
    Number.isFinite(total) &&
    total > 0;
  const progress = measurable ? Math.min(100, (processed / total) * 100) : null;
  const progressLabel =
    progress === null
      ? null
      : new Intl.NumberFormat("es-PE", { maximumFractionDigits: 1 }).format(
          Math.floor(progress * 10) / 10,
        );
  const offline = active && activity?.worker_online === false;
  const explanation = failed
    ? run.error ||
      "No se pudo completar esta etapa. Consulta el detalle del procesamiento para reanudarla."
    : cancelled
      ? "El trabajo se detuvo. Los resultados registrados se conservan."
      : offline
        ? "No se recibe una señal reciente del servicio de procesamiento. El archivo permanece guardado."
        : queued
          ? "El archivo está guardado y espera que el servicio inicie esta etapa."
          : ingestion
            ? "Organizando las filas y agrupando las ubicaciones del archivo."
            : active
              ? "El trabajo continúa en el servidor. Puedes salir y consultar el avance al volver."
              : completed
                ? "La etapa terminó. Puedes consultar los resultados o continuar con las ubicaciones pendientes."
                : "El detalle de actividad estará disponible cuando se inicie el trabajo.";

  return (
    <section
      className={`run-activity run-activity--${state}${offline ? " run-activity--offline" : ""}`}
      aria-label="Actividad del procesamiento"
    >
      <div className="run-activity__main">
        <div className="run-activity__content">
          <div className="run-activity__eyebrow">
            <span className="run-activity__status" role="status">
              <Icon
                size={15}
                className={
                  active && !queued ? "run-activity__spinner" : undefined
                }
                aria-hidden="true"
              />
              {status}
            </span>
            <span>{stage ? `Etapa · ${stage}` : "Archivo PNP"}</span>
          </div>
          <h2>{title}</h2>
          <div className="run-activity__file">
            <FileSpreadsheet size={19} aria-hidden="true" />
            <span title={run.filename}>{run.filename}</span>
          </div>
        </div>
        <div className="run-activity__time">
          <span>
            <Clock3 size={15} aria-hidden="true" />
            {queued
              ? "Tiempo en cola"
              : active
                ? "Tiempo transcurrido"
                : stage
                  ? "Duración de esta etapa"
                  : "Duración de esta ejecución"}
          </span>
          <div
            role="timer"
            aria-live="off"
            className={timer ? undefined : "run-activity__time-unknown"}
          >
            {timer ?? "Tiempo no disponible"}
          </div>
          {timer && <small>horas : minutos : segundos</small>}
        </div>
      </div>
      {active && (
        <div className="run-activity__progress">
          <div className="run-activity__progress-label">
            <span>
              {measurable
                ? `${number(Math.min(processed, total))} de ${number(total)} ubicaciones evaluadas en esta etapa`
                : queued
                  ? "Esperando inicio"
                  : ingestion
                    ? "Preparando ubicaciones"
                    : "Preparando el avance de esta etapa"}
            </span>
            {progressLabel !== null && <strong>{progressLabel} %</strong>}
          </div>
          <div
            className="run-activity__track"
            role="progressbar"
            aria-label="Avance de la etapa actual"
            aria-valuemin={0}
            aria-valuemax={100}
            aria-valuenow={progress ?? undefined}
            aria-valuetext={
              progressLabel !== null
                ? `${progressLabel} %`
                : "Avance todavía no disponible"
            }
          >
            <span
              className={progress === null ? "is-indeterminate" : undefined}
              style={
                progress === null
                  ? undefined
                  : { transform: `scaleX(${progress / 100})` }
              }
            />
          </div>
        </div>
      )}
      <p
        className={`run-activity__message${offline ? " run-activity__message--warning" : ""}`}
        role={failed ? "alert" : undefined}
      >
        {offline && <AlertCircle size={16} aria-hidden="true" />}
        {explanation}
      </p>
    </section>
  );
}
