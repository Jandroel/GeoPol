import { useMemo, useState, type CSSProperties } from "react";
import { useInfiniteQuery, useQuery } from "@tanstack/react-query";
import { Link, useSearchParams } from "react-router-dom";
import {
  ChartNoAxesCombined,
  Download,
  MapPin,
  Layers3,
  CircleOff,
  ListFilter,
} from "lucide-react";
import { request } from "../lib/api";
import { date, isActiveRun, label, number } from "../lib/format";
import { percentage, qualityFlagLabel, reviewStateLabel } from "../lib/quality";
import type { Page, Run } from "../types";
import {
  Badge,
  Empty,
  ErrorNotice,
  Loading,
  PageHeader,
  Pagination,
} from "../components/ui";
import { ExportPanel } from "../components/ExportPanel";
import { ResultsTable } from "../components/ResultsTable";
import {
  StatisticsMap,
  statisticLayers,
  type StatisticLayer,
  type StatisticsFeature,
} from "../components/StatisticsMap";
import "./Statistics.css";

export interface StatisticsData {
  run_id: string;
  generated_at: string;
  totals: {
    units: number;
    source_rows: number;
    accepted: number;
    mapped: number;
    without_accepted_geometry: number;
    excluded: number;
    issue_rows: number;
  };
  resolutions: { resolution: string; units: number }[];
  flags: { flag: number | null; units: number }[];
  review_states: { state: string | null; units: number }[];
  districts: {
    ubigeo: string;
    district: string | null;
    name_conflict: boolean;
    units: number;
    source_rows: number;
    mapped: number;
  }[];
  map: {
    features: StatisticsFeature[];
    total: number;
    shown: number;
    limit: number;
    truncated: boolean;
    layers: Partial<Record<StatisticLayer, number>>;
  };
}
const tabs = [
  ["summary", "Resumen"],
  ["records", "Detalle de registros"],
  ["exports", "Descargas"],
];

const resolutionTone = (resolution: string) =>
  (
    ({
      ACEPTADO_AUTOMATICO: "green",
      ACEPTADO_MANUAL: "blue",
      REVISION_REQUERIDA: "amber",
      SIN_COINCIDENCIA: "rose",
      INFORMACION_INSUFICIENTE: "orange",
      NO_EVALUABLE_REFERENCIA: "purple",
      ERROR_TECNICO: "red",
      EXCLUIDO_FLAG_10: "slate",
    }) as Record<string, string>
  )[resolution] ?? "slate";

function ResolutionDistribution({ data }: { data: StatisticsData }) {
  const [selected, setSelected] = useState<string | null>(null);
  const [focused, setFocused] = useState<string | null>(null);
  const active = focused ?? selected;
  const detail = data.resolutions.find((item) => item.resolution === active);
  let offset = 0;
  return (
    <div
      className="statistics-distribution"
      onKeyDown={(event) => {
        if (event.key === "Escape") {
          setSelected(null);
          setFocused(null);
        }
      }}
    >
      <div className="statistics-resolution-body">
        <div className="statistics-donut" aria-hidden="true">
          <svg viewBox="0 0 140 140">
            <circle cx="70" cy="70" r="55" className="statistics-ring-track" />
            {data.resolutions.map((item) => {
              const share = data.totals.units
                ? (item.units / data.totals.units) * 100
                : 0;
              const start = offset;
              offset += share;
              return (
                <circle
                  key={item.resolution}
                  cx="70"
                  cy="70"
                  r="55"
                  pathLength="100"
                  strokeDasharray={`${share} ${100 - share}`}
                  strokeDashoffset={-start}
                  transform="rotate(-90 70 70)"
                  className={`statistics-ring-segment${active && active !== item.resolution ? " is-muted" : ""}`}
                  style={{
                    stroke: `var(--statistics-${resolutionTone(item.resolution)})`,
                  }}
                  onMouseEnter={() => setFocused(item.resolution)}
                  onMouseLeave={() => setFocused(null)}
                />
              );
            })}
          </svg>
          <div className="statistics-donut-center">
            <strong>
              {percentage(
                detail?.units ?? data.totals.mapped,
                data.totals.units,
              )}
            </strong>
            <span>{detail ? "seleccionado" : "con geometría"}</span>
          </div>
        </div>
        <div
          className="statistics-resolution-list"
          aria-label="Distribución por resolución"
        >
          {data.resolutions.map((item) => (
            <button
              key={item.resolution}
              type="button"
              aria-pressed={selected === item.resolution}
              className={active === item.resolution ? "is-active" : ""}
              onMouseEnter={() => setFocused(item.resolution)}
              onMouseLeave={() => setFocused(null)}
              onFocus={() => setFocused(item.resolution)}
              onBlur={() => setFocused(null)}
              onClick={() =>
                setSelected(
                  selected === item.resolution ? null : item.resolution,
                )
              }
            >
              <i
                aria-hidden="true"
                style={{
                  background: `var(--statistics-${resolutionTone(item.resolution)})`,
                }}
              />
              <span>{label(item.resolution)}</span>
              <strong>{number(item.units)}</strong>
              <small>{percentage(item.units, data.totals.units)}</small>
            </button>
          ))}
        </div>
      </div>
      <p className="statistics-chart-detail" role="status">
        {detail
          ? `${label(detail.resolution)}: ${number(detail.units)} ubicaciones (${percentage(detail.units, data.totals.units)}).`
          : "Selecciona una categoría para explorar su proporción."}
      </p>
    </div>
  );
}

export function Statistics() {
  const [params, setParams] = useSearchParams();
  const runId = params.get("run_id") ?? "";
  const tab = tabs.some(([key]) => key === params.get("tab"))
    ? params.get("tab")!
    : "summary";
  const runs = useInfiniteQuery({
    queryKey: ["statistics-runs"],
    initialPageParam: 1,
    queryFn: ({ pageParam }) =>
      request<Page<Run>>(`/runs?page=${pageParam}&page_size=100`),
    getNextPageParam: (last) =>
      last.page * last.page_size < last.total ? last.page + 1 : undefined,
  });
  const selected = useQuery({
    queryKey: ["run", runId],
    queryFn: () => request<Run>(`/runs/${runId}`),
    enabled: !!runId,
    refetchInterval: (query) =>
      isActiveRun(query.state.data?.status) ? 3000 : false,
  });
  const items = runs.data?.pages.flatMap((page) => page.items) ?? [];
  return (
    <>
      <PageHeader
        title="Estadística"
        description="Explora los resultados, su distribución territorial y los archivos de salida de cada procesamiento."
      />
      <section className="panel statistics-selector">
        <label>
          Procesamiento a consultar
          <select
            value={runId}
            onChange={(event) =>
              setParams(
                event.target.value ? { run_id: event.target.value } : {},
              )
            }
          >
            <option value="">Selecciona un procesamiento</option>
            {runId && !items.some((item) => item.id === runId) && (
              <option value={runId}>
                {selected.data?.name ?? "Procesamiento seleccionado"}
              </option>
            )}
            {items.map((run) => (
              <option key={run.id} value={run.id}>
                {run.name}
                {run.superseded_by ? " · histórico" : ""} · {label(run.status)}
              </option>
            ))}
          </select>
        </label>
        {selected.data && (
          <div className="statistics-source">
            <Layers3 size={21} aria-hidden="true" />
            <div>
              <strong>{selected.data.filename}</strong>
              <span>Creado {date(selected.data.created_at)}</span>
            </div>
            <Badge value={selected.data.status} />
          </div>
        )}
        {runs.hasNextPage && (
          <button
            className="text-link plain-button"
            disabled={runs.isFetchingNextPage}
            onClick={() => void runs.fetchNextPage()}
          >
            Cargar más procesamientos
          </button>
        )}
        <ErrorNotice error={runs.error} />
      </section>
      {!runId ? (
        <Empty
          title="Elige un procesamiento para ver sus resultados"
          text="Los indicadores se calculan sobre todas sus ubicaciones. El mapa utiliza los resultados geográficos aceptados."
          action={
            <Link className="button secondary" to="/runs">
              Ver historial de procesamientos
            </Link>
          }
        />
      ) : selected.isPending ? (
        <Loading />
      ) : selected.isError ? (
        <ErrorNotice error={selected.error} />
      ) : (
        <>
          <div
            className="tabs"
            role="tablist"
            aria-label="Secciones de estadística"
          >
            {tabs.map(([key, title]) => (
              <button
                key={key}
                role="tab"
                id={`statistics-tab-${key}`}
                aria-controls={`statistics-panel-${key}`}
                aria-selected={tab === key}
                className={tab === key ? "active" : ""}
                onClick={() => setParams({ run_id: runId, tab: key })}
              >
                {title}
              </button>
            ))}
          </div>
          <div
            role="tabpanel"
            id={`statistics-panel-${tab}`}
            aria-labelledby={`statistics-tab-${tab}`}
          >
            {tab === "summary" ? (
              <StatisticsSummary key={runId} run={selected.data} />
            ) : tab === "records" ? (
              <ResultsTable
                runId={runId}
                live={isActiveRun(selected.data.status)}
                runVersion={`${selected.data.status}:${selected.data.processed_units}`}
              />
            ) : ["COMPLETED", "COMPLETED_WITH_ISSUES"].includes(
                selected.data.status,
              ) ? (
              <ExportPanel key={runId} runId={runId} />
            ) : (
              <Empty
                title="La descarga se habilita al finalizar"
                text="El procesamiento debe terminar para exportar una instantánea completa de sus resultados."
              />
            )}
          </div>
        </>
      )}
    </>
  );
}

function StatisticsSummary({ run }: { run: Run }) {
  const [mapLimit, setMapLimit] = useState(2000);
  const [district, setDistrict] = useState<string | null>(null);
  const [districtPage, setDistrictPage] = useState(1);
  const [layers, setLayers] = useState<StatisticLayer[]>([
    "original",
    "reference",
    "manual",
    "other",
  ]);
  const query = useQuery({
    queryKey: ["statistics", run.id, mapLimit, run.status],
    queryFn: () =>
      request<StatisticsData>(
        `/runs/${run.id}/statistics?map_limit=${mapLimit}`,
      ),
    refetchInterval: isActiveRun(run.status) ? 15000 : false,
  });
  const features = useMemo(
    () =>
      (query.data?.map.features ?? []).filter(
        (feature) =>
          layers.includes(feature.properties.layer) &&
          (district === null || feature.properties.ubigeo === district),
      ),
    [query.data, layers, district],
  );
  if (query.isPending)
    return <Loading text="Calculando estadísticas del procesamiento…" />;
  if (query.isError) return <ErrorNotice error={query.error} />;
  const data = query.data;
  const attention = data.resolutions.filter(
    (item) =>
      !["ACEPTADO_AUTOMATICO", "ACEPTADO_MANUAL", "EXCLUIDO_FLAG_10"].includes(
        item.resolution,
      ),
  );
  return (
    <div className="statistics-content">
      <div className="statistics-scope">
        <span>
          Resultados vigentes dentro del procesamiento seleccionado
          {run.superseded_by ? " · Ejecución histórica" : ""}. Cantidades
          expresadas en unidades de ubicación.
        </span>
        <span>Consulta: {date(data.generated_at)}</span>
      </div>
      {isActiveRun(run.status) && (
        <div className="notice">
          El procesamiento está en curso. Los resultados y las cantidades
          todavía pueden cambiar.
        </div>
      )}
      <div className="statistics-kpis">
        {[
          {
            label: "Filas originales",
            value: data.totals.source_rows,
            detail: "Se conserva el archivo de origen",
            icon: Layers3,
            tone: "blue",
          },
          {
            label: "Unidades de ubicación",
            value: data.totals.units,
            detail: "Denuncias y lugares agrupados",
            icon: ListFilter,
            tone: "purple",
          },
          {
            label: "Con geometría aceptada",
            value: data.totals.mapped,
            detail: `${percentage(data.totals.mapped, data.totals.units)} del total de ubicaciones`,
            icon: MapPin,
            tone: "green",
          },
          {
            label: "Excluidas · flag 10",
            value: data.totals.excluded,
            detail: "Fuera de geocodificación",
            icon: CircleOff,
            tone: "slate",
          },
        ].map((metric) => (
          <article
            className={`statistics-kpi statistics-tone-${metric.tone}`}
            key={metric.label}
          >
            <metric.icon size={20} aria-hidden="true" />
            <span>{metric.label}</span>
            <strong>{number(metric.value)}</strong>
            <small>{metric.detail}</small>
          </article>
        ))}
      </div>
      <div className="statistics-overview">
        <section className="panel statistics-map-panel">
          <div className="panel-heading">
            <h2>Mapa de resultados</h2>
            <label className="statistics-map-limit">
              Máximo de geometrías
              <select
                value={mapLimit}
                onChange={(event) => setMapLimit(Number(event.target.value))}
              >
                <option value={500}>500</option>
                <option value={2000}>2,000</option>
                <option value={5000}>5,000</option>
              </select>
            </label>
          </div>
          <div className="statistics-layers" aria-label="Capas del mapa">
            {Object.entries(statisticLayers).map(([key, layer]) => (
              <label
                key={key}
                style={
                  {
                    "--layer-color": `var(--statistics-${key}, ${layer.color})`,
                  } as CSSProperties
                }
              >
                <input
                  type="checkbox"
                  checked={layers.includes(key as StatisticLayer)}
                  onChange={(event) =>
                    setLayers(
                      event.target.checked
                        ? [...layers, key as StatisticLayer]
                        : layers.filter((value) => value !== key),
                    )
                  }
                />
                <i aria-hidden="true" />
                <span>{layer.label}</span>
                <strong>
                  {number(data.map.layers[key as StatisticLayer])}
                </strong>
              </label>
            ))}
          </div>
          {district !== null && (
            <div className="statistics-map-filter">
              Distrito en mapa: UBIGEO {district || "no declarado"}
              <button
                className="text-link plain-button"
                onClick={() => setDistrict(null)}
              >
                Ver todos
              </button>
            </div>
          )}
          <StatisticsMap features={features} />
          <p className="statistics-map-note">
            Vista actual: {number(features.length)} de {number(data.map.total)}{" "}
            ubicaciones con geometría aceptada.{" "}
            {data.map.truncated
              ? `La muestra del mapa contiene ${number(data.map.shown)} geometrías; los indicadores y tablas incluyen todas las ubicaciones.`
              : "Las capas permiten explorar la muestra sin cambiar los indicadores."}
          </p>
          <p className="statistics-map-note">
            Las líneas y áreas conservan su geometría; no representan puertas
            exactas. Las capas describen el método, no certifican una entidad de
            origen.
          </p>
        </section>
        <div className="statistics-side">
          <section className="panel statistics-resolution">
            <div className="panel-heading">
              <h2>Resumen de resolución</h2>
              <ChartNoAxesCombined size={21} aria-hidden="true" />
            </div>
            <ResolutionDistribution data={data} />
            <p className="field-hint">
              Una aceptación puede conservar una dirección sin geometría. El
              mapa incluye únicamente puntos, líneas o áreas válidas y
              aceptadas.
            </p>
          </section>
          <section className="panel statistics-districts">
            <div className="panel-heading">
              <div>
                <h2>Distribución territorial</h2>
                <p>UBIGEO y distrito declarado en el archivo</p>
              </div>
            </div>
            <div className="table-scroll">
              <table>
                <thead>
                  <tr>
                    <th>Distrito / UBIGEO</th>
                    <th>Ubicaciones</th>
                    <th>Con geometría</th>
                    <th>Mapa</th>
                  </tr>
                </thead>
                <tbody>
                  {data.districts
                    .slice((districtPage - 1) * 10, districtPage * 10)
                    .map((item) => (
                      <tr key={item.ubigeo}>
                        <th scope="row">
                          <span>
                            {item.district ||
                              (item.name_conflict
                                ? "Nombres distintos en origen"
                                : "Sin nombre declarado")}
                          </span>
                          <small>{item.ubigeo || "Sin UBIGEO"}</small>
                        </th>
                        <td>{number(item.units)}</td>
                        <td>
                          <span>{percentage(item.mapped, item.units)}</span>
                          <progress
                            max={Math.max(item.units, 1)}
                            value={item.mapped}
                            aria-label={`Geometrías aceptadas en ${item.ubigeo || "sin UBIGEO"}`}
                          />
                        </td>
                        <td>
                          <button
                            className="button secondary icon"
                            aria-label={`Ver UBIGEO ${item.ubigeo || "sin código"} en el mapa`}
                            onClick={() => {
                              setDistrict(item.ubigeo);
                              document
                                .querySelector(".statistics-map-panel")
                                ?.scrollIntoView({
                                  behavior: window.matchMedia(
                                    "(prefers-reduced-motion: reduce)",
                                  ).matches
                                    ? "instant"
                                    : "smooth",
                                  block: "start",
                                });
                            }}
                          >
                            <MapPin size={17} aria-hidden="true" />
                          </button>
                        </td>
                      </tr>
                    ))}
                </tbody>
              </table>
            </div>
            {data.districts.length > 10 && (
              <Pagination
                page={districtPage}
                total={data.districts.length}
                pageSize={10}
                onChange={setDistrictPage}
              />
            )}
            {!data.districts.length && (
              <p className="field-hint">
                Aún no hay ubicaciones para distribuir.
              </p>
            )}
          </section>
        </div>
      </div>
      <div className="statistics-bottom">
        <section className="panel statistics-breakdown statistics-tone-amber">
          <h2>Estados pendientes</h2>
          <p>
            Clasificación actual del resultado; no equivale a una causa
            comprobada.
          </p>
          {attention.length ? (
            attention.map((item) => (
              <div
                key={item.resolution}
                className="statistics-breakdown-row"
                style={
                  {
                    "--row-color": `var(--statistics-${resolutionTone(item.resolution)})`,
                  } as CSSProperties
                }
              >
                <span>{label(item.resolution)}</span>
                <strong>{number(item.units)}</strong>
                <progress
                  max={Math.max(data.totals.units, 1)}
                  value={item.units}
                  aria-label={`${label(item.resolution)}: ${percentage(item.units, data.totals.units)}`}
                />
              </div>
            ))
          ) : (
            <p>No hay ubicaciones pendientes en este procesamiento.</p>
          )}
        </section>
        <section className="panel statistics-breakdown statistics-tone-purple">
          <h2>Flags de calidad</h2>
          <p>
            Describen la ubicación y su exclusión; se separan de la revisión.
          </p>
          {data.flags.map((item) => (
            <div
              key={item.flag ?? "none"}
              className="statistics-breakdown-row"
              style={
                {
                  "--row-color": `var(--statistics-${item.flag === 1 ? "blue" : item.flag === 2 ? "purple" : "slate"})`,
                } as CSSProperties
              }
            >
              <span>
                {item.flag === null
                  ? "Sin flag evaluado"
                  : qualityFlagLabel(item.flag)}
              </span>
              <strong>{number(item.units)}</strong>
              <progress
                max={Math.max(data.totals.units, 1)}
                value={item.units}
                aria-label={`${item.flag === null ? "Sin flag evaluado" : qualityFlagLabel(item.flag)}: ${percentage(item.units, data.totals.units)}`}
              />
            </div>
          ))}
        </section>
        <section className="panel statistics-breakdown statistics-tone-blue">
          <h2>Estado de revisión</h2>
          <p>Situación vigente de cada ubicación.</p>
          {data.review_states.map((item) => (
            <div key={item.state ?? "none"}>
              <span>
                {item.state
                  ? reviewStateLabel(item.state)
                  : "Sin estado de calidad evaluado"}
              </span>
              <strong>{number(item.units)}</strong>
            </div>
          ))}
          <Link className="text-link" to={`/quality?run_id=${run.id}`}>
            Consultar seguimiento por etapa
          </Link>
        </section>
      </div>
      <section className="panel statistics-download">
        <Download size={24} aria-hidden="true" />
        <div>
          <h2>Descargar resultados</h2>
          <p>
            En la pestaña Descargas puedes generar el Excel o CSV y su
            manifiesto de trazabilidad.
          </p>
        </div>
        <Link
          className="button secondary"
          to={`/statistics?run_id=${run.id}&tab=exports`}
        >
          Ir a descargas
        </Link>
      </section>
    </div>
  );
}
