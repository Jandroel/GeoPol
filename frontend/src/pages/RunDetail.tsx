import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Link,
  useNavigate,
  useParams,
  useSearchParams,
} from "react-router-dom";
import { ArrowLeft, Square } from "lucide-react";
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
import { ReprocessPanel } from "../components/ReprocessPanel";
import { RunReadinessPanel } from "../components/RunReadinessPanel";
export function RunDetail() {
  const { id } = useParams();
  const [searchParams, setSearchParams] = useSearchParams();
  const { user } = useAuth();
  const navigate = useNavigate();
  const client = useQueryClient();
  const [error, setError] = useState<unknown>();
  const [busy, setBusy] = useState(false);
  const tab = ["results", "exports", "config", "reprocess"].includes(
    searchParams.get("tab") ?? "",
  )
    ? searchParams.get("tab")!
    : "results";
  const setTab = (value: string) => setSearchParams({ tab: value });
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
        title={run.name}
        description={`Creado ${date(run.created_at)}`}
        actions={<Badge value={run.status} />}
      />
      <ErrorNotice error={error || run.error} />
      {run.superseded_by && (
        <Notice>
          Esta ejecución se conserva como histórico y ya no aparece en la
          bandeja vigente.{" "}
          <Link className="inline-link" to={`/runs/${run.superseded_by}`}>
            Abrir la ejecución que la sustituye
          </Link>
          .
        </Notice>
      )}
      {run.parent_run_id && (
        <Notice>
          Este procesamiento procede de una ejecución anterior.{" "}
          <Link className="inline-link" to={`/runs/${run.parent_run_id}`}>
            Consultar su historial y decisiones
          </Link>
          .
        </Notice>
      )}
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
      {run.counts_by_product && (
        <section
          className="automatic-summary panel"
          aria-label="Aceptaciones automáticas por producto"
        >
          <div>
            <span>Automáticas con punto</span>
            <strong>{number(run.counts_by_product.PUNTO ?? 0)}</strong>
          </div>
          <div>
            <span>Automáticas con área o tramo</span>
            <strong>{number(run.counts_by_product.AREA_TRAMO ?? 0)}</strong>
            <small>
              Geometría de referencia; no representa una puerta exacta.
            </small>
          </div>
        </section>
      )}
      {!active && !run.superseded_by && tab === "results" && (
        <RunReadinessPanel runId={run.id} canManage={canManage} />
      )}
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
      {canManage &&
        (active || ["FAILED", "CANCELLED"].includes(run.status)) && (
          <div className="run-meta">
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
                <button
                  className="button secondary"
                  disabled={busy}
                  onClick={() => void action("retry")}
                >
                  Reanudar
                </button>
              )}
            </div>
          </div>
        )}
      <div
        className="tabs"
        role="tablist"
        aria-label="Información del procesamiento"
      >
        {[
          ["results", "Resultados"],
          ["exports", "Exportaciones"],
          ["config", "Configuración"],
          ...(canManage && !active ? [["reprocess", "Reprocesar"]] : []),
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
        ) : tab === "reprocess" && canManage && !active ? (
          <ReprocessPanel key={run.id} run={run} />
        ) : (
          <section className="panel form-panel">
            <h2>Datos de la ejecución</h2>
            <dl className="key-values">
              <div>
                <dt>Archivo de origen</dt>
                <dd>{run.filename}</dd>
              </div>
              <div>
                <dt>Versión de reglas</dt>
                <dd>{run.rules_version}</dd>
              </div>
              <div>
                <dt>Referencia</dt>
                <dd>
                  {run.reference_id ? "Catálogo versionado" : "Sin catálogo"}
                </dd>
              </div>
              <div>
                <dt>Inicio</dt>
                <dd>{date(run.started_at)}</dd>
              </div>
            </dl>
            <details>
              <summary>Configuración técnica preservada</summary>
              <pre>{JSON.stringify(run.config, null, 2)}</pre>
            </details>
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
