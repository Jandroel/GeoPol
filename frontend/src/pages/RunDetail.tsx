import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useNavigate, useParams } from "react-router-dom";
import { ArrowLeft, RotateCcw, Square } from "lucide-react";
import { useAuth } from "../auth";
import { post, request } from "../lib/api";
import { date, isActiveRun, label, number } from "../lib/format";
import type { Run } from "../types";
import {
  Badge,
  ErrorNotice,
  Loading,
  Notice,
  PageHeader,
} from "../components/ui";
import { ResultsTable } from "../components/ResultsTable";
import { ExportPanel } from "../components/ExportPanel";
export function RunDetail() {
  const { id } = useParams();
  const { user } = useAuth();
  const navigate = useNavigate();
  const client = useQueryClient();
  const [error, setError] = useState<unknown>();
  const [busy, setBusy] = useState(false);
  const [tab, setTab] = useState("results");
  const query = useQuery({
    queryKey: ["run", id],
    queryFn: () => request<Run>(`/runs/${id}`),
    refetchInterval: (q) => (isActiveRun(q.state.data?.status) ? 2000 : false),
  });
  async function action(actionName: string) {
    setBusy(true);
    setError(null);
    try {
      const run = await post<Run>(`/runs/${id}/${actionName}`);
      await client.invalidateQueries({ queryKey: ["run", id] });
      if (actionName === "reprocess") navigate(`/runs/${run.id}`);
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  }
  if (query.isPending) return <Loading />;
  if (query.isError) return <ErrorNotice error={query.error} />;
  const run = query.data;
  const active = isActiveRun(run.status);
  const canManage = ["admin", "operator"].includes(user?.role ?? "");
  return (
    <>
      <Link className="back-link" to="/runs">
        <ArrowLeft size={16} aria-hidden="true" />
        Procesamientos
      </Link>
      <PageHeader
        eyebrow="DETALLE DEL PROCESAMIENTO"
        title={run.name}
        description={`${run.filename} · Creado ${date(run.created_at)}`}
        actions={<Badge value={run.status} />}
      />
      <ErrorNotice error={error || run.error} />
      {active && (
        <Notice>
          El trabajo se ejecuta en el servidor. Puedes cerrar esta ventana y
          consultar el avance al volver.
        </Notice>
      )}
      <div className="run-summary panel">
        <div>
          <span>Filas de origen</span>
          <strong>{number(run.source_rows)}</strong>
        </div>
        <div>
          <span>Unidades de ubicación</span>
          <strong>{number(run.location_units)}</strong>
        </div>
        <div>
          <span>Unidades procesadas</span>
          <strong>{number(run.processed_units)}</strong>
        </div>
        <div>
          <span>Filas con incidencias</span>
          <strong>{number(run.issue_rows)}</strong>
        </div>
      </div>
      {active && (
        <div className="processing-progress">
          <progress
            value={run.processed_units}
            max={Math.max(1, run.location_units)}
          />
          <span>
            {label(run.status)} · {number(run.processed_units)} /{" "}
            {number(run.location_units)} unidades
          </span>
        </div>
      )}
      <div className="run-meta">
        <span>
          Reglas <strong>{run.rules_version}</strong>
        </span>
        <span>
          Referencia{" "}
          <strong>
            {run.reference_id ? "Catálogo versionado" : "Sin catálogo"}
          </strong>
        </span>
        <span>
          Inicio <strong>{date(run.started_at)}</strong>
        </span>
        {canManage && (
          <div className="button-row">
            {active ? (
              <button
                className="button secondary"
                disabled={busy}
                onClick={() => void action("cancel")}
              >
                <Square size={14} aria-hidden="true" />
                Cancelar
              </button>
            ) : (
              <>
                {["FAILED", "CANCELLED"].includes(run.status) && (
                  <button
                    className="button secondary"
                    disabled={busy}
                    onClick={() => void action("retry")}
                  >
                    Reanudar
                  </button>
                )}
                <button
                  className="button secondary"
                  disabled={busy}
                  onClick={() => void action("reprocess")}
                >
                  <RotateCcw size={15} aria-hidden="true" />
                  Reprocesar
                </button>
              </>
            )}
          </div>
        )}
      </div>
      <div
        className="tabs"
        role="tablist"
        aria-label="Información del procesamiento"
      >
        {[
          ["results", "Resultados"],
          ["exports", "Exportaciones"],
          ["config", "Configuración"],
        ].map(([key, title]) => (
          <button
            role="tab"
            aria-selected={tab === key}
            aria-controls={`panel-${key}`}
            id={`tab-${key}`}
            className={tab === key ? "active" : ""}
            key={key}
            onClick={() => setTab(key)}
          >
            {title}
          </button>
        ))}
      </div>
      <div role="tabpanel" id={`panel-${tab}`} aria-labelledby={`tab-${tab}`}>
        {tab === "results" ? (
          <ResultsTable
            runId={id}
            live={active}
            runVersion={`${run.status}:${run.processed_units}`}
          />
        ) : tab === "exports" ? (
          <ExportPanel runId={id!} />
        ) : (
          <section className="panel form-panel">
            <h2>Configuración preservada</h2>
            <pre>{JSON.stringify(run.config, null, 2)}</pre>
            <h3>Conteo por resolución</h3>
            <div className="key-values">
              {Object.entries(run.counts ?? {}).map(([key, value]) => (
                <div key={key}>
                  <span>{label(key)}</span>
                  <strong>{number(value)}</strong>
                </div>
              ))}
            </div>
          </section>
        )}
      </div>
    </>
  );
}
