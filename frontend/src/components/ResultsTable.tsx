import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useLocation } from "react-router-dom";
import { Search } from "lucide-react";
import { request } from "../lib/api";
import { label } from "../lib/format";
import type { LocationResult, Page } from "../types";
import { Badge, Empty, ErrorNotice, Loading, Pagination, ViewLink } from "./ui";
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
}: {
  runId?: string;
  review?: boolean;
  live?: boolean;
  runVersion?: string;
}) {
  const location = useLocation();
  const [page, setPage] = useState(1);
  const [q, setQ] = useState("");
  const [search, setSearch] = useState("");
  const [resolution, setResolution] = useState("");
  const query = useQuery({
    // A terminal run snapshot must fetch final rows even when periodic polling stops.
    queryKey: ["results", runId, review, page, search, resolution, runVersion],
    queryFn: () =>
      request<Page<LocationResult>>(
        `${review ? "/review" : `/runs/${runId}/results`}?page=${page}&page_size=25&q=${encodeURIComponent(search)}&resolution=${resolution}`,
      ),
    refetchInterval: live ? 5000 : false,
  });
  return (
    <section className="panel">
      <div className="table-toolbar">
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
      {query.isPending ? (
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
          <Pagination page={page} total={query.data.total} onChange={setPage} />
        </>
      )}
    </section>
  );
}
