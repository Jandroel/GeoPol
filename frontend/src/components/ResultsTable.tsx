import { useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useLocation } from "react-router-dom";
import { Search } from "lucide-react";
import { request } from "../lib/api";
import { label, number } from "../lib/format";
import {
  qualityFlagLabel,
  qualityStageLabel,
  reviewStateLabel,
} from "../lib/quality";
import type { LocationResult, Page } from "../types";
import { Badge, Empty, ErrorNotice, Loading, Pagination, ViewLink } from "./ui";
import "./results-table.css";

const pageSize = 25;
export const resolutions = [
  "ACEPTADO_AUTOMATICO",
  "ACEPTADO_MANUAL",
  "REVISION_REQUERIDA",
  "SIN_COINCIDENCIA",
  "INFORMACION_INSUFICIENTE",
  "NO_EVALUABLE_REFERENCIA",
  "ERROR_TECNICO",
];
export function ResultsTable({
  runId,
  review = false,
  live = false,
  runVersion,
  qualityFlag,
  qualityStage,
  reviewState,
}: {
  runId?: string;
  review?: boolean;
  live?: boolean;
  runVersion?: string;
  qualityFlag?: number;
  qualityStage?: string;
  reviewState?: string;
}) {
  const location = useLocation();
  const [q, setQ] = useState("");
  const [search, setSearch] = useState("");
  const [resolution, setResolution] = useState("");
  const scope = JSON.stringify([
    runId,
    review,
    search,
    resolution,
    qualityFlag,
    qualityStage,
    reviewState,
  ]);
  const [pagination, setPagination] = useState({ scope, page: 1 });
  // A changed filter starts at page 1 before its request is made, including
  // externally supplied quality/review filters that do not remount this table.
  const page = pagination.scope === scope ? pagination.page : 1;
  const setPage = (next: number) => setPagination({ scope, page: next });
  const query = useQuery({
    // A terminal run snapshot must fetch final rows even when periodic polling stops.
    queryKey: [
      "results",
      runId,
      review,
      page,
      search,
      resolution,
      runVersion,
      qualityFlag,
      qualityStage,
      reviewState,
    ],
    queryFn: () =>
      request<Page<LocationResult>>(
        `${review ? "/review" : `/runs/${runId}/results`}?page=${page}&page_size=${pageSize}&q=${encodeURIComponent(search)}&resolution=${resolution}${qualityFlag !== undefined ? `&quality_flag=${qualityFlag}` : ""}${qualityStage ? `&quality_stage=${encodeURIComponent(qualityStage)}` : ""}${reviewState ? `&review_state=${encodeURIComponent(reviewState)}` : ""}`,
      ),
    refetchInterval: live ? 5000 : false,
  });
  const responsePageSize = query.data?.page_size ?? pageSize;
  const lastPage = Math.max(
    1,
    Math.ceil((query.data?.total ?? 0) / responsePageSize),
  );
  const pageOutOfRange = query.isSuccess && page > lastPage;
  useEffect(() => {
    if (pagination.scope !== scope) {
      setPagination({ scope, page: 1 });
      return;
    }
    // A live update may remove the last page. Return to an existing page rather
    // than showing an empty table beside a nonzero total and an invalid range.
    if (pageOutOfRange) setPagination({ scope, page: lastPage });
  }, [pageOutOfRange, lastPage, scope, pagination.scope]);
  const filtered = !!(
    search ||
    resolution ||
    qualityFlag !== undefined ||
    qualityStage ||
    reviewState
  );
  const totalLabel = filtered
    ? "Ubicaciones en este filtro"
    : review
      ? "Ubicaciones en esta bandeja"
      : "Total de ubicaciones";
  const rangeStart = query.data?.items.length
    ? (page - 1) * responsePageSize + 1
    : 0;
  const rangeEnd = query.data?.items.length
    ? Math.min(query.data.total, rangeStart + query.data.items.length - 1)
    : 0;
  return (
    <section className="panel results-panel">
      <div className="table-toolbar">
        <div
          className="results-total"
          role="status"
          aria-label="Total de resultados"
          aria-live="polite"
          aria-atomic="true"
        >
          <span className="results-total-label">{totalLabel}</span>
          {query.isError ? (
            <span className="results-total-message">Total no disponible</span>
          ) : !query.data || pageOutOfRange ? (
            <span className="results-total-message">Consultando total…</span>
          ) : (
            <>
              <strong>{number(query.data.total)}</strong>
              <span className="results-total-range">
                {query.data.total === 0
                  ? "Sin ubicaciones para mostrar"
                  : !query.data.items.length
                    ? "Esta página aún no tiene ubicaciones"
                    : `Mostrando ${number(rangeStart)}–${number(rangeEnd)} de ${number(query.data.total)}`}
              </span>
            </>
          )}
        </div>
        <form
          className="search-form"
          onSubmit={(e) => {
            e.preventDefault();
            setSearch(q);
            setPage(1);
          }}
        >
          <Search size={18} aria-hidden="true" />
          <label className="sr-only" htmlFor="result-search">
            Buscar denuncia o dirección
          </label>
          <input
            id="result-search"
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="Buscar denuncia o dirección…"
          />
          <button className="button secondary" type="submit">
            Buscar
          </button>
        </form>
        {!review && (
          <label className="filter-label">
            <span>Resolución</span>
            <select
              aria-label="Resolución"
              value={resolution}
              onChange={(e) => {
                setResolution(e.target.value);
                setPage(1);
              }}
            >
              <option value="">Todos los estados</option>
              {resolutions.map((r) => (
                <option key={r} value={r}>
                  {label(r)}
                </option>
              ))}
            </select>
          </label>
        )}
      </div>
      {query.isPending || pageOutOfRange ? (
        <Loading />
      ) : query.isError ? (
        <ErrorNotice error={query.error} />
      ) : (
        <>
          {query.data.items.length ? (
            <div className="table-scroll">
              <table>
                <thead>
                  <tr>
                    <th>Denuncia / ubicación</th>
                    <th>UBIGEO</th>
                    <th>Resolución</th>
                    <th>Flag / etapa</th>
                    <th>Estado de revisión</th>
                    <th>Precisión</th>
                    <th>Producto</th>
                    <th>
                      <span className="sr-only">Acciones</span>
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {query.data.items.map((result) => (
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
                      </td>
                      <td className="mono">{result.ubigeo || "—"}</td>
                      <td>
                        <Badge value={result.resolution} />
                      </td>
                      <td className="quality-cell">
                        <strong>{qualityFlagLabel(result.quality_flag)}</strong>
                        <small>{qualityStageLabel(result.quality_stage)}</small>
                      </td>
                      <td>{reviewStateLabel(result.review_state)}</td>
                      <td>{label(result.precision)}</td>
                      <td>{label(result.product)}</td>
                      <td>
                        <ViewLink
                          to={`/results/${result.id}?back=${encodeURIComponent(location.pathname + location.search)}`}
                        >
                          Examinar
                        </ViewLink>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <Empty
              title={
                review && !search
                  ? "No hay ubicaciones pendientes"
                  : "No hay resultados para mostrar"
              }
              text={
                review && !search
                  ? "Las ubicaciones que necesiten una decisión aparecerán en esta bandeja."
                  : "Prueba otra búsqueda o espera a que avance el procesamiento."
              }
            />
          )}
          <Pagination
            page={page}
            total={query.data.total}
            pageSize={responsePageSize}
            onChange={setPage}
          />
        </>
      )}
    </section>
  );
}
