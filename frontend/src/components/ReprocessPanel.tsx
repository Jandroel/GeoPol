import { useState, type FormEvent } from "react";
import {
  useInfiniteQuery,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";
import { Link, useNavigate } from "react-router-dom";
import { ArrowRight, Database } from "lucide-react";
import { post, request } from "../lib/api";
import type { Page, ProcessingDefaults, Reference, Run } from "../types";
import { ErrorNotice, Notice } from "./ui";
import { CoordinatePolicy, documentedCrs } from "./CoordinatePolicy";
import { ReferenceCapability } from "./ReferenceCapability";

export function ReprocessPanel({ run }: { run: Run }) {
  const [reference, setReference] = useState(run.reference_id ?? "default");
  const [crsConfirmed, setCrsConfirmed] = useState(documentedCrs(run.config));
  const [crsEvidence, setCrsEvidence] = useState(
    documentedCrs(run.config) ? String(run.config.crs_evidence) : "",
  );
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
  const defaults = useQuery({
    queryKey: ["processing-defaults"],
    queryFn: () => request<ProcessingDefaults>("/processing-defaults"),
  });
  const selectedCatalog =
    reference === "default"
      ? defaults.data?.catalog
      : items.find((item) => item.id === reference);
  const defaultUnavailable =
    reference === "default" && defaults.data?.status !== "ready";
  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const result = await post<Run>(`/runs/${run.id}/reprocess`, {
        reference_id:
          reference === "default"
            ? defaults.data?.default_reference_id
            : reference || null,
        crs: crsConfirmed ? "EPSG:4326" : null,
        crs_evidence: crsConfirmed ? crsEvidence.trim() : null,
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
      <ErrorNotice error={error || references.error || defaults.error} />
      <div className="form-grid">
        <label>
          Catálogo del nuevo procesamiento
          <select
            aria-label="Catálogo del nuevo procesamiento"
            value={reference}
            onChange={(event) => setReference(event.target.value)}
            disabled={busy || references.isPending}
          >
            <option value="default">
              {defaults.data?.status === "ready"
                ? `Referencia base · ${defaults.data.catalog?.name}`
                : "Referencia base no disponible"}
            </option>
            <option value="">Procesar explícitamente sin catálogo</option>
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
      {selectedCatalog && <ReferenceCapability catalog={selectedCatalog} />}
      {defaultUnavailable && (
        <Notice>
          Configura una referencia base o selecciona otra opción para continuar.
        </Notice>
      )}
      {run.config.crs === "EPSG:4326" && !documentedCrs(run.config) && (
        <Notice>
          La ejecución anterior asumió WGS84 sin una fuente de confirmación. El
          nuevo procesamiento no heredará esa suposición.
        </Notice>
      )}
      <CoordinatePolicy
        confirmed={crsConfirmed}
        evidence={crsEvidence}
        onConfirmed={setCrsConfirmed}
        onEvidence={setCrsEvidence}
        disabled={busy}
      />
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
          disabled={
            busy ||
            references.isPending ||
            references.isError ||
            defaults.isPending ||
            defaultUnavailable ||
            (crsConfirmed && crsEvidence.trim().length < 8)
          }
        >
          {busy ? "Creando ejecución…" : "Crear nuevo procesamiento"}
          <ArrowRight size={17} aria-hidden="true" />
        </button>
      </div>
    </form>
  );
}
