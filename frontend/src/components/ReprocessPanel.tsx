import { useState, type FormEvent } from "react";
import { useInfiniteQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useNavigate } from "react-router-dom";
import { ArrowRight, Database } from "lucide-react";
import { post, request } from "../lib/api";
import type { Page, Reference, Run } from "../types";
import { ErrorNotice, Notice } from "./ui";

export function ReprocessPanel({ run }: { run: Run }) {
  const [reference, setReference] = useState(run.reference_id ?? "");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>();
  const navigate = useNavigate();
  const client = useQueryClient();
  const references = useInfiniteQuery({
    queryKey: ["reprocess-references"],
    initialPageParam: 1,
    queryFn: ({ pageParam }) =>
      request<Page<Reference>>(`/references?page=${pageParam}&page_size=100`),
    getNextPageParam: (last) =>
      last.page * last.page_size < last.total ? last.page + 1 : undefined,
  });
  const items = references.data?.pages.flatMap((page) => page.items) ?? [];
  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const result = await post<Run>(`/runs/${run.id}/reprocess`, {
        reference_id: reference || null,
      });
      await client.invalidateQueries({ queryKey: ["runs"] });
      navigate(`/runs/${result.id}`);
    } catch (error) {
      setError(error);
    } finally {
      setBusy(false);
    }
  }
  return (
    <form className="panel form-panel" onSubmit={submit}>
      <div className="panel-heading">
        <div>
          <h2>Crear un nuevo procesamiento</h2>
          <p>
            Usa el mismo archivo y mapeo, con la referencia que selecciones.
          </p>
        </div>
        <Database size={24} className="teal" aria-hidden="true" />
      </div>
      <ErrorNotice error={error || references.error} />
      <div className="form-grid">
        <label>
          Catálogo del nuevo procesamiento
          <select
            aria-label="Catálogo del nuevo procesamiento"
            value={reference}
            onChange={(event) => setReference(event.target.value)}
            disabled={busy || references.isPending}
          >
            <option value="">Sin catálogo de referencia</option>
            {run.reference_id &&
              !items.some((item) => item.id === run.reference_id) && (
                <option value={run.reference_id}>
                  Catálogo de la ejecución actual
                </option>
              )}
            {items.map((item) => (
              <option key={item.id} value={item.id}>
                {item.name} · {item.version}
              </option>
            ))}
          </select>
        </label>
      </div>
      {references.hasNextPage && (
        <button
          type="button"
          className="text-link plain-button"
          disabled={references.isFetchingNextPage}
          onClick={() => void references.fetchNextPage()}
        >
          Cargar más catálogos
        </button>
      )}
      <Notice>
        La ejecución actual y sus decisiones se conservan. Al terminar
        correctamente el nuevo procesamiento, esta ejecución pasará al histórico
        de la bandeja. Si falla, seguirá vigente.
      </Notice>
      {!reference && (
        <Notice>
          Sin catálogo, las búsquedas que necesiten una referencia seguirán
          expresando esa limitación. Este reproceso no garantiza aceptar
          ubicaciones.
        </Notice>
      )}
      <div className="form-actions">
        <Link className="text-link" to="/references">
          Gestionar catálogos
        </Link>
        <button
          className="button primary"
          disabled={busy || references.isPending || references.isError}
        >
          {busy ? "Creando ejecución…" : "Crear nuevo procesamiento"}
          <ArrowRight size={17} aria-hidden="true" />
        </button>
      </div>
    </form>
  );
}
