import { useState } from "react";
import {
  useInfiniteQuery,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";
import { Link, useSearchParams } from "react-router-dom";
import {
  ArrowRight,
  Database,
  FileSpreadsheet,
  ListChecks,
} from "lucide-react";
import { useAuth } from "../auth";
import { post, request } from "../lib/api";
import { date, isActiveRun, number } from "../lib/format";
import type { Page, QualityOverview, Reference, Run } from "../types";
import {
  Badge,
  Empty,
  ErrorNotice,
  Loading,
  Notice,
  PageHeader,
} from "../components/ui";
import { RunActivity } from "../components/RunActivity";
import { QualityProgressCard } from "../components/QualityProgressCard";
import "./procedures.css";

const procedures = [
  {
    name: "Normalización",
    kind: "normalization",
    detail:
      "Estandariza los campos, reconoce componentes y conserva el texto original y las transformaciones. Se ejecuta al preparar las ubicaciones del archivo.",
  },
  {
    name: "Puerta",
    kind: "door",
    detail:
      "Contrasta vía, número de puerta, territorio y punto de referencia. Solo acepta automáticamente coincidencias con evidencia suficiente; los candidatos ambiguos se conservan para revisión.",
  },
  {
    name: "Cuadra",
    kind: "block",
    detail:
      "Busca la cuadra declarada y conserva la geometría real del tramo. No deduce la cuadra a partir del número de puerta ni genera un domicilio exacto.",
  },
  {
    name: "Cruce de vías",
    kind: "intersection",
    detail:
      "Contrasta las dos vías y una intersección documentada dentro del territorio. Después, el motor también dispone de una etapa de vías antes de continuar con núcleos.",
  },
  {
    name: "Núcleos urbanos",
    kind: "nucleus",
    detail:
      "Contrasta núcleos y centros poblados identificados. Un punto de centro poblado representa esa localidad y conserva esa precisión; no acredita una puerta.",
  },
  {
    name: "Jurisdicción",
    kind: "jurisdiction",
    detail:
      "Contrasta la jurisdicción explícita y su geometría. El distrito por sí solo no identifica una jurisdicción policial.",
  },
  {
    name: "Coordenadas",
    kind: "coordinates",
    detail:
      "Las coordenadas intervienen en las comprobaciones de coherencia, CRS y territorio. En el flujo por calidad este control está integrado: no existe una ejecución independiente que permita omitir las comprobaciones de cada etapa.",
  },
  {
    name: "Sitios de interés",
    kind: "sites",
    detail:
      "La cobertura actual incluye puntos de centros poblados en la etapa de núcleos. La búsqueda general de establecimientos o sitios de interés no está disponible como procedimiento independiente.",
  },
];

type BundleReference = Omit<Reference, "config"> & {
  config?: Reference["config"] & {
    reference_bundle?: {
      catalogs: Pick<
        Reference,
        "id" | "name" | "version" | "source" | "feature_count"
      >[];
    };
  };
};

export function Procedures() {
  const [params, setParams] = useSearchParams();
  const runId = params.get("run_id") ?? "";
  const runs = useInfiniteQuery({
    queryKey: ["procedure-runs"],
    initialPageParam: 1,
    queryFn: ({ pageParam }) =>
      request<Page<Run>>(`/runs?page=${pageParam}&page_size=50`),
    getNextPageParam: (last) =>
      last.page * last.page_size < last.total ? last.page + 1 : undefined,
  });
  const selected = useQuery({
    queryKey: ["run", runId],
    queryFn: () => request<Run>(`/runs/${runId}`),
    enabled: !!runId,
    refetchInterval: (query) =>
      isActiveRun(query.state.data?.status) ? 2000 : false,
  });
  const items = runs.data?.pages.flatMap((page) => page.items) ?? [];
  return (
    <>
      <PageHeader
        title="Procedimientos"
        description="Ejecuta las etapas sobre los pendientes y conserva las ubicaciones ya resueltas."
      />
      <section className="panel procedure-selector">
        <label>
          Procesamiento a consultar
          <select
            value={runId}
            onChange={(event) => {
              const next = new URLSearchParams(params);
              if (event.target.value) next.set("run_id", event.target.value);
              else next.delete("run_id");
              setParams(next);
            }}
          >
            <option value="">Selecciona un procesamiento</option>
            {runId && !items.some((run) => run.id === runId) && (
              <option value={runId}>
                {selected.data?.name ?? "Procesamiento seleccionado"}
              </option>
            )}
            {items.map((run) => (
              <option key={run.id} value={run.id}>
                {run.name}
                {run.superseded_by ? " · histórico" : ""}
              </option>
            ))}
          </select>
        </label>
        {runs.hasNextPage && (
          <button
            className="button secondary"
            disabled={runs.isFetchingNextPage}
            onClick={() => void runs.fetchNextPage()}
          >
            {runs.isFetchingNextPage
              ? "Cargando…"
              : "Cargar más procesamientos"}
          </button>
        )}
        {runs.isPending && <span role="status">Cargando procesamientos…</span>}
        <ErrorNotice error={runs.error} />
      </section>
      {!runId ? (
        <Empty
          title="Selecciona el archivo que quieres procesar"
          text="El selector incluye las ejecuciones existentes. Para iniciar una nueva, carga el archivo y revisa sus columnas en Validación."
          action={
            <Link className="button primary" to="/">
              Ir a carga de archivos <ArrowRight size={16} aria-hidden="true" />
            </Link>
          }
        />
      ) : selected.isPending ? (
        <Loading />
      ) : selected.isError ? (
        <ErrorNotice error={selected.error} />
      ) : (
        <ProcedureRun key={runId} run={selected.data} />
      )}
    </>
  );
}

function ProcedureRun({ run }: { run: Run }) {
  const { user } = useAuth();
  const client = useQueryClient();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>();
  const active = isActiveRun(run.status);
  const quality = run.config.workflow === "quality_v1";
  const canManage = ["admin", "operator"].includes(user?.role ?? "");
  const summary = useQuery({
    queryKey: ["quality", run.id, run.status, run.processed_units],
    queryFn: () => request<QualityOverview>(`/runs/${run.id}/quality`),
    enabled: quality,
    refetchInterval: active ? 2500 : 15000,
  });
  const catalog = useQuery({
    queryKey: ["reference", run.reference_id],
    queryFn: () => request<BundleReference>(`/references/${run.reference_id}`),
    enabled: !!run.reference_id,
  });
  const references =
    catalog.data?.config?.reference_bundle?.catalogs ??
    (catalog.data ? [catalog.data] : []);
  async function advance(stage: string) {
    setBusy(true);
    setError(null);
    try {
      await post<Run>(`/runs/${run.id}/advance`, { stage });
      await Promise.all(
        [
          "run",
          "quality",
          "results",
          "runs",
          "procedure-runs",
          "review-summary",
        ].map((key) => client.invalidateQueries({ queryKey: [key] })),
      );
    } catch (reason) {
      setError(reason);
    } finally {
      setBusy(false);
    }
  }
  return (
    <div className="procedure-workspace">
      <aside
        className="procedure-context"
        aria-label="Archivo y referencias del procesamiento"
      >
        <section className="panel procedure-file">
          <div className="procedure-section-title">
            <FileSpreadsheet size={20} aria-hidden="true" />
            <h2>Archivo de origen</h2>
          </div>
          <strong className="procedure-file-name">{run.filename}</strong>
          <p>{run.name}</p>
          <Badge value={run.status} />
          <dl>
            <div>
              <dt>Filas de origen</dt>
              <dd>{number(run.source_rows)}</dd>
            </div>
            <div>
              <dt>Ubicaciones agrupadas</dt>
              <dd>{number(run.location_units)}</dd>
            </div>
            <div>
              <dt>Creado</dt>
              <dd>{date(run.created_at)}</dd>
            </div>
          </dl>
          <Link className="text-link" to={`/runs/${run.id}?tab=config`}>
            Ver configuración
          </Link>
        </section>
        <section className="panel procedure-references">
          <div className="procedure-section-title">
            <Database size={20} aria-hidden="true" />
            <h2>Referencias utilizadas</h2>
          </div>
          {!run.reference_id ? (
            <p>
              Sin catálogo en esta ejecución. Las carencias de referencia se
              conservan en los resultados.
            </p>
          ) : catalog.isPending ? (
            <Loading text="Consultando referencias…" />
          ) : catalog.isError ? (
            <ErrorNotice error={catalog.error} />
          ) : (
            <ul>
              {references.map((reference) => (
                <li key={reference.id}>
                  <strong>{reference.name}</strong>
                  <span>
                    {reference.version} · {reference.source}
                  </span>
                  <small>
                    {number(reference.feature_count)} elementos disponibles
                  </small>
                </li>
              ))}
            </ul>
          )}
        </section>
      </aside>
      <div className="procedure-main">
        <RunActivity run={run} />
        {run.superseded_by && (
          <Notice>
            Ejecución histórica.{" "}
            <Link
              className="inline-link"
              to={`/procedures?run_id=${run.superseded_by}`}
            >
              Abrir su reemplazo
            </Link>
            .
          </Notice>
        )}
        {quality ? (
          summary.isPending ? (
            <Loading text="Consultando avance…" />
          ) : summary.isError ? (
            <ErrorNotice error={summary.error} />
          ) : (
            <QualityProgressCard
              data={summary.data}
              active={active}
              busy={busy}
              canManage={canManage}
              superseded={!!run.superseded_by}
              onAdvance={(stage) => void advance(stage)}
              error={<ErrorNotice error={error} />}
            />
          )
        ) : (
          <Notice>
            Esta ejecución utiliza el flujo anterior. Sus resultados e historial
            siguen disponibles; no admite avance por etapas.
          </Notice>
        )}
        <section
          className="panel procedure-methods"
          aria-labelledby="procedure-methods-title"
        >
          <div className="procedure-section-title">
            <ListChecks size={20} aria-hidden="true" />
            <h2 id="procedure-methods-title">Procedimientos y alcance</h2>
          </div>
          <p className="procedure-methods-hint">
            Abre un procedimiento para consultar qué comprueba. El avance
            disponible se muestra arriba y sigue el orden del motor.
          </p>
          <div className="procedure-method-grid">
            {procedures.map((procedure, index) => {
              const stage = summary.data?.stages.find(
                (item) => item.key === procedure.kind,
              );
              const state =
                procedure.kind === "normalization"
                  ? "Integrado en la carga"
                  : procedure.kind === "coordinates"
                    ? "Control integrado"
                    : procedure.kind === "sites"
                      ? "Cobertura limitada"
                      : stage?.units
                        ? `${number(stage.units)} evaluadas`
                        : "Sin evaluación registrada";
              return (
                <details key={procedure.kind} className="procedure-method">
                  <summary>
                    <span className="procedure-number">{index + 1}</span>
                    <span>
                      <strong>{procedure.name}</strong>
                      <small>{state}</small>
                    </span>
                  </summary>
                  <p>{procedure.detail}</p>
                </details>
              );
            })}
          </div>
        </section>
        <div className="procedure-actions">
          <Link className="button primary" to={`/statistics?run_id=${run.id}`}>
            Ver estadística <ArrowRight size={17} aria-hidden="true" />
          </Link>
          <Link className="button secondary" to={`/review?run_id=${run.id}`}>
            Revisar ubicaciones
          </Link>
          <Link className="button secondary" to={`/runs/${run.id}?tab=results`}>
            Resultados y exportaciones
          </Link>
        </div>
      </div>
    </div>
  );
}
