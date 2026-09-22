import { useEffect, useState, type FormEvent } from "react";
import { useInfiniteQuery, useQuery } from "@tanstack/react-query";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import {
  ArrowRight,
  ClipboardCheck,
  Database,
  Search,
  Wrench,
  FileQuestion,
} from "lucide-react";
import { useAuth } from "../auth";
import { request } from "../lib/api";
import { date, number } from "../lib/format";
import {
  readReviewFilters,
  reservationIsLive,
  reviewBuckets,
  reviewParams,
  reviewReason,
  type ReviewFilters,
  type ReviewBucket,
} from "../lib/review";
import type { LocationResult, Page, ReviewSummary, Run } from "../types";
import {
  Badge,
  Empty,
  ErrorNotice,
  Loading,
  Notice,
  PageHeader,
  Pagination,
} from "../components/ui";
const icons = {
  actionable: ClipboardCheck,
  needs_reference: Database,
  needs_data: FileQuestion,
  technical: Wrench,
};
export function Review() {
  const [params, setParams] = useSearchParams();
  const filters = readReviewFilters(params);
  const [search, setSearch] = useState(filters.q);
  const [busy, setBusy] = useState(false);
  const [nextError, setNextError] = useState<unknown>();
  const [nextEmpty, setNextEmpty] = useState(false);
  const navigate = useNavigate();
  const { user } = useAuth();
  const canReview = ["admin", "reviewer"].includes(user?.role ?? "");
  useEffect(() => setSearch(filters.q), [filters.q]);
  const searchParams = reviewParams(filters);
  const summaryParams = new URLSearchParams({
    include_superseded: String(filters.includeSuperseded),
  });
  if (filters.runId) summaryParams.set("run_id", filters.runId);
  if (filters.q) summaryParams.set("q", filters.q);
  const summary = useQuery({
    queryKey: ["review-summary", summaryParams.toString()],
    queryFn: () => request<ReviewSummary>(`/review/summary?${summaryParams}`),
    refetchInterval: 15000,
  });
  const queue = useQuery({
    queryKey: ["review-queue", searchParams.toString()],
    queryFn: () => request<Page<LocationResult>>(`/review?${searchParams}`),
    refetchInterval: 15000,
  });
  const runs = useInfiniteQuery({
    queryKey: ["review-runs"],
    initialPageParam: 1,
    queryFn: ({ pageParam }) =>
      request<Page<Run>>(`/runs?page=${pageParam}&page_size=100`),
    getNextPageParam: (last) =>
      last.page * last.page_size < last.total ? last.page + 1 : undefined,
  });
  const runItems = runs.data?.pages.flatMap((page) => page.items) ?? [];
  const back = `/review?${searchParams}`;
  function update(changes: Partial<ReviewFilters>) {
    setNextEmpty(false);
    setNextError(null);
    setParams(reviewParams({ ...filters, page: 1, ...changes }));
  }
  function submitSearch(event: FormEvent) {
    event.preventDefault();
    update({ q: search });
  }
  async function next() {
    setBusy(true);
    setNextError(null);
    setNextEmpty(false);
    try {
      const result = await request<{ item: LocationResult | null }>(
        `/review/next?${reviewParams({ ...filters, stage: "open", page: 1 })}`,
      );
      if (result.item)
        navigate(`/results/${result.item.id}?back=${encodeURIComponent(back)}`);
      else setNextEmpty(true);
    } catch (error) {
      setNextError(error);
    } finally {
      setBusy(false);
    }
  }
  return (
    <>
      <PageHeader
        title="Revisión de ubicaciones"
        actions={
          canReview &&
          filters.bucket === "actionable" &&
          filters.stage !== "closed" && (
            <button
              className="button primary"
              disabled={busy || queue.isPending}
              onClick={() => void next()}
            >
              {busy ? "Buscando…" : "Abrir siguiente disponible"}
              <ArrowRight size={17} aria-hidden="true" />
            </button>
          )
        }
      />
      <div className="review-scope">
        <span>
          El resumen corresponde a la ejecución y búsqueda seleccionadas.
        </span>
        <button
          className="text-link plain-button"
          onClick={() => update({ stage: "closed", bucket: "all" })}
        >
          Finalizados: {summary.data ? number(summary.data.closed) : "—"}
        </button>
      </div>
      <ErrorNotice error={summary.error} />
      <div className="review-facets">
        {(Object.keys(reviewBuckets) as ReviewBucket[]).map((bucket) => {
          const Icon = icons[bucket];
          return (
            <button
              type="button"
              key={bucket}
              className={`review-facet ${filters.bucket === bucket && filters.stage === "open" ? "selected" : ""}`}
              aria-pressed={
                filters.bucket === bucket && filters.stage === "open"
              }
              onClick={() => update({ bucket, stage: "open" })}
            >
              <span>
                <Icon size={19} aria-hidden="true" />
                {reviewBuckets[bucket].label}
              </span>
              <strong>
                {summary.data ? number(summary.data.open[bucket]) : "—"}
              </strong>
              <small>{reviewBuckets[bucket].description}</small>
            </button>
          );
        })}
      </div>
      {filters.stage !== "closed" &&
        !!summary.data &&
        (summary.data.open.needs_reference > 0 ||
          summary.data.open.needs_data > 0) && (
          <Notice>
            <strong>Primero resuelve las causas compartidas.</strong> Los casos
            sin referencia necesitan cobertura y reprocesamiento; los datos
            incompletos requieren corregir o corroborar la fuente del lote. La
            bandeja accionable reúne los casos con evidencia para decidir.
            <div className="button-row">
              <Link className="text-link" to="/references">
                Gestionar referencia base
              </Link>
              {filters.runId && (
                <Link
                  className="text-link"
                  to={`/runs/${filters.runId}?tab=reprocess`}
                >
                  Preparar reprocesamiento
                </Link>
              )}
            </div>
          </Notice>
        )}
      <section className="panel review-filter-panel">
        <div className="review-filters">
          <label>
            Ejecución
            <select
              aria-label="Ejecución"
              value={filters.runId}
              onChange={(e) => update({ runId: e.target.value })}
            >
              <option value="">
                {filters.includeSuperseded
                  ? "Todas las ejecuciones"
                  : "Todas las ejecuciones vigentes"}
              </option>
              {filters.runId &&
                !runItems.some((run) => run.id === filters.runId) && (
                  <option value={filters.runId}>
                    Ejecución seleccionada · {filters.runId.slice(0, 8)}
                  </option>
                )}
              {runItems.map((run) => (
                <option key={run.id} value={run.id}>
                  {run.name}
                  {run.superseded_by ? " · histórica" : ""}
                </option>
              ))}
            </select>
          </label>
          <label>
            Motivo de atención
            <select
              aria-label="Motivo de atención"
              value={filters.bucket}
              onChange={(e) =>
                update({ bucket: e.target.value as ReviewFilters["bucket"] })
              }
            >
              <option value="all">Todos los motivos</option>
              {Object.entries(reviewBuckets).map(([key, value]) => (
                <option key={key} value={key}>
                  {value.label}
                </option>
              ))}
            </select>
          </label>
          <label>
            Etapa
            <select
              aria-label="Etapa"
              value={filters.stage}
              onChange={(e) =>
                update({
                  stage: e.target.value as ReviewFilters["stage"],
                  bucket: e.target.value === "closed" ? "all" : filters.bucket,
                })
              }
            >
              <option value="open">Pendientes</option>
              <option value="closed">Finalizados</option>
              <option value="all">Pendientes y finalizados</option>
            </select>
          </label>
        </div>
        <div className="review-search-row">
          <form className="search-form" onSubmit={submitSearch}>
            <Search size={17} aria-hidden="true" />
            <label className="sr-only" htmlFor="queue-search">
              Buscar denuncia, dirección o UBIGEO
            </label>
            <input
              id="queue-search"
              maxLength={100}
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Denuncia, dirección o UBIGEO"
            />
            <button className="button secondary">Buscar</button>
          </form>
          <label className="checkbox-label">
            <input
              type="checkbox"
              checked={filters.includeSuperseded}
              onChange={(e) => update({ includeSuperseded: e.target.checked })}
            />
            Incluir ejecuciones sustituidas
          </label>
        </div>
        {runs.hasNextPage && (
          <button
            className="text-link plain-button"
            disabled={runs.isFetchingNextPage}
            onClick={() => void runs.fetchNextPage()}
          >
            Cargar más ejecuciones en el selector
          </button>
        )}
        <ErrorNotice error={runs.error} />
      </section>
      {filters.bucket === "needs_reference" && filters.stage !== "closed" && (
        <Notice>
          Estos registros necesitan una fuente evaluable. Puedes{" "}
          <Link to="/references" className="inline-link">
            importar un catálogo
          </Link>{" "}
          y crear un nuevo procesamiento con esa referencia desde el detalle de
          la ejecución. Importar una fuente no modifica los resultados
          históricos.
        </Notice>
      )}
      {filters.bucket === "needs_data" && filters.stage !== "closed" && (
        <Notice>
          Completa o corrobora los datos en el archivo de origen y carga una
          versión corregida para tratar estos casos en conjunto. No hace falta
          registrar una decisión individual por cada dato ausente; si se decide
          cerrar sin punto, debe existir una conclusión documentada.
        </Notice>
      )}
      {filters.bucket === "technical" && filters.stage !== "closed" && (
        <Notice>
          Consulta el procesamiento y su configuración antes de asignar una
          ubicación. Una decisión manual no corrige el problema técnico de
          origen.
        </Notice>
      )}
      {filters.stage === "closed" && (
        <Notice>
          Finalizados incluye resoluciones automáticas y decisiones manuales
          cerradas. Un registro finalizado puede conservar una dirección sin
          punto o permanecer sin resolver.
        </Notice>
      )}
      <ErrorNotice error={nextError} />
      {nextEmpty && (
        <Notice>
          No hay registros disponibles en esta selección. Puede haber reservas
          vigentes de otros revisores. Los bloqueos y el historial siguen
          disponibles en sus filtros.
        </Notice>
      )}
      <section className="panel">
        {queue.isPending ? (
          <Loading />
        ) : queue.isError ? (
          <ErrorNotice error={queue.error} />
        ) : (
          <>
            {queue.data.items.length ? (
              <div className="table-scroll">
                <table>
                  <thead>
                    <tr>
                      <th>Denuncia / ubicación</th>
                      <th>Motivo y resolución</th>
                      <th>Candidatos</th>
                      <th>Revisión</th>
                      <th>
                        <span className="sr-only">Acciones</span>
                      </th>
                    </tr>
                  </thead>
                  <tbody>
                    {queue.data.items.map((result) => (
                      <tr key={result.id}>
                        <td className="location-cell">
                          <strong>
                            {result.complaint_id || "Sin identificador"}
                          </strong>
                          <span>
                            {result.location_normalized ||
                              result.location_original ||
                              "Sin dirección recuperable"}
                          </span>
                          <small className="muted">
                            UBIGEO {result.ubigeo || "no disponible"}
                          </small>
                        </td>
                        <td className="review-reason-cell">
                          <span className="reason-title">
                            {result.review_bucket === "none"
                              ? "Finalizado"
                              : reviewBuckets[result.review_bucket]?.label}
                          </span>
                          <p>{reviewReason(result.reason)}</p>
                          <Badge value={result.resolution} />
                        </td>
                        <td className="numeric">
                          {number(result.candidate_count)}
                        </td>
                        <td>
                          <strong className="review-state">
                            {result.review_status === "CLOSED"
                              ? "Finalizado"
                              : "Pendiente"}
                          </strong>
                          {result.review_owner &&
                          reservationIsLive(result.review_expires_at) ? (
                            <small className="reservation-note">
                              {result.review_owner === user?.id
                                ? "Reservado por ti"
                                : "Reserva de otro revisor"}
                              <br />
                              Hasta {date(result.review_expires_at)}
                            </small>
                          ) : result.review_status === "OPEN" ? (
                            <small className="reservation-note">
                              Sin reserva
                            </small>
                          ) : null}
                        </td>
                        <td>
                          <Link
                            className="text-link"
                            to={`/results/${result.id}?back=${encodeURIComponent(back)}`}
                          >
                            Examinar
                            <ArrowRight size={15} aria-hidden="true" />
                          </Link>
                          <Link
                            className="row-sub-link"
                            to={`/runs/${result.run_id}`}
                          >
                            Ver ejecución
                          </Link>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <Empty
                title={
                  filters.stage === "closed"
                    ? "No hay finalizados en esta selección"
                    : "No hay pendientes en esta selección"
                }
                text={
                  filters.bucket === "actionable"
                    ? "Revisa las tarjetas de referencia, datos y atención técnica. No todos los pendientes requieren una decisión individual ahora."
                    : "Cambia los filtros para consultar otras categorías o ejecuciones."
                }
              />
            )}
            <Pagination
              page={filters.page}
              total={queue.data.total}
              onChange={(page) => update({ page })}
            />
          </>
        )}
      </section>
    </>
  );
}
