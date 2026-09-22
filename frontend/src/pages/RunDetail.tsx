import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Link,
  useNavigate,
  useParams,
  useSearchParams,
} from "react-router-dom";
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
import { ReprocessPanel } from "../components/ReprocessPanel";
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
        eyebrow="DETALLE DEL PROCESAMIENTO"
        title={run.name}
        description={`${run.filename} · Creado ${date(run.created_at)}`}
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
      {!active && !run.reference_id && (
        <Notice>
          El procesamiento terminó sin un catálogo de referencia. Consulta los
          motivos de atención antes de revisar registros individualmente.
          {canManage && (
            <button
              className="text-link plain-button"
              onClick={() => setTab("reprocess")}
            >
              Seleccionar referencia y preparar reproceso
            </button>
          )}
        </Notice>
      )}
      {!active && (
        <div className="run-review-link">
          <Link
            className="button secondary"
            to={`/review?run_id=${run.id}&bucket=actionable&stage=open${run.superseded_by ? "&include_superseded=true" : ""}`}
          >
            Abrir revisión de esta ejecución
          </Link>
          <span>
            Los bloqueos de referencia, datos y atención técnica se muestran por
            separado.
          </span>
        </div>
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
            <small>La precisión se conserva en cada resultado.</small>
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
                  onClick={() => setTab("reprocess")}
                >
                  <RotateCcw size={15} aria-hidden="true" />
                  Preparar reproceso
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
          ...(canManage && !active
            ? [["reprocess", "Nuevo procesamiento"]]
            : []),
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
