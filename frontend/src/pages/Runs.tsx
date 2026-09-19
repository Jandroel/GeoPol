import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { Plus } from "lucide-react";
import { useAuth } from "../auth";
import { request } from "../lib/api";
import type { Page, Run } from "../types";
import { ErrorNotice, Loading, PageHeader, Pagination } from "../components/ui";
import { RunTable } from "../components/RunTable";
export function Runs() {
  const [page, setPage] = useState(1);
  const { user } = useAuth();
  const query = useQuery({
    queryKey: ["runs", page],
    queryFn: () => request<Page<Run>>(`/runs?page=${page}&page_size=25`),
    refetchInterval: 10000,
  });
  return (
    <>
      <PageHeader
        eyebrow="PROCESAMIENTO DE DATOS"
        title="Procesamientos"
        description="Cada ejecución conserva sus reglas, referencias y resultados."
        actions={
          ["admin", "operator"].includes(user?.role ?? "") && (
            <Link className="button primary" to="/runs/new">
              <Plus size={18} aria-hidden="true" />
              Nuevo procesamiento
            </Link>
          )
        }
      />
      <section className="panel">
        {query.isPending ? (
          <Loading />
        ) : query.isError ? (
          <ErrorNotice error={query.error} />
        ) : (
          <>
            <RunTable runs={query.data.items} />
            <Pagination
              page={page}
              total={query.data.total}
              onChange={setPage}
            />
          </>
        )}
      </section>
    </>
  );
}
