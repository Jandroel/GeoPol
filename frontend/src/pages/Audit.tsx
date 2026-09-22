import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { request } from "../lib/api";
import { date, displayValue, label } from "../lib/format";
import type { Page } from "../types";
import { ErrorNotice, Loading, PageHeader, Pagination } from "../components/ui";
interface AuditEvent {
  id: string;
  actor: string;
  action: string;
  entity_id: string;
  created_at: string;
  detail: unknown;
}
export function Audit() {
  const [page, setPage] = useState(1);
  const query = useQuery({
    queryKey: ["audit", page],
    queryFn: () =>
      request<Page<AuditEvent>>(`/audit?page=${page}&page_size=25`),
  });
  return (
    <>
      <PageHeader
        title="Auditoría"
        description="Registro de acciones sobre archivos, referencias, resultados y exportaciones."
      />
      <section className="panel">
        {query.isPending ? (
          <Loading />
        ) : query.isError ? (
          <ErrorNotice error={query.error} />
        ) : (
          <>
            <div className="table-scroll">
              <table>
                <thead>
                  <tr>
                    <th>Fecha</th>
                    <th>Actor</th>
                    <th>Acción</th>
                    <th>Entidad</th>
                    <th>Detalle</th>
                  </tr>
                </thead>
                <tbody>
                  {query.data.items.map((event) => (
                    <tr key={event.id}>
                      <td className="nowrap">{date(event.created_at)}</td>
                      <td>{event.actor}</td>
                      <td>{label(event.action)}</td>
                      <td className="mono">{event.entity_id}</td>
                      <td>
                        <details>
                          <summary>Ver detalle</summary>
                          <pre>{displayValue(event.detail)}</pre>
                        </details>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
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
