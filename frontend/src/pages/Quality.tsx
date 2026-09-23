import { useInfiniteQuery, useQuery } from "@tanstack/react-query";
import { Link, useSearchParams } from "react-router-dom";
import { request } from "../lib/api";
import { isActiveRun } from "../lib/format";
import type { Page, Run } from "../types";
import { Empty, ErrorNotice, Loading, PageHeader } from "../components/ui";
import { QualityPanel } from "../components/QualityPanel";
import { RunActivity } from "../components/RunActivity";
export function Quality() {
  const [params, setParams] = useSearchParams();
  const runId = params.get("run_id") ?? "";
  const runs = useInfiniteQuery({
    queryKey: ["quality-runs"],
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
      isActiveRun(query.state.data?.status) ? 2000 : false,
  });
  const items = runs.data?.pages.flatMap((page) => page.items) ?? [];
  return (
    <>
      <PageHeader
        title="Seguimiento por calidad"
        description="Consulta cantidades, porcentajes y descargas de cada etapa del procesamiento."
      />
      <section className="panel form-panel">
        <label>
          Procesamiento a consultar
          <select
            value={runId}
            onChange={(e) =>
              setParams(e.target.value ? { run_id: e.target.value } : {})
            }
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
                {run.config.workflow !== "quality_v1"
                  ? " · flujo anterior"
                  : ""}
              </option>
            ))}
          </select>
        </label>
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
      {runId ? (
        selected.isPending ? (
          <Loading />
        ) : selected.isError ? (
          <ErrorNotice error={selected.error} />
        ) : (
          <>
            <RunActivity run={selected.data} />
            <QualityPanel key={runId} run={selected.data} />
          </>
        )
      ) : (
        <Empty
          title="Selecciona un procesamiento"
          text="El seguimiento conserva las ubicaciones resueltas y distingue las que necesitan revisión de las que pueden seguir a la próxima etapa."
          action={
            <Link className="button secondary" to="/runs/new">
              Ir a carga de archivos
            </Link>
          }
        />
      )}
    </>
  );
}
