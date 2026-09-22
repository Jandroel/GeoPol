import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Download, FileCheck2 } from "lucide-react";
import { useAuth } from "../auth";
import { downloadAuthenticated, post, request } from "../lib/api";
import type { ExportJob } from "../types";
import { ErrorNotice } from "./ui";
import { label, number } from "../lib/format";
export function ExportPanel({ runId }: { runId: string }) {
  const { user } = useAuth();
  const [profile, setProfile] = useState("locations");
  const key = `geopol.export.${user?.id}.${runId}`;
  const [jobId, setJobId] = useState(() => localStorage.getItem(key) ?? "");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>();
  const job = useQuery({
    queryKey: ["export", jobId],
    queryFn: () => request<ExportJob>(`/exports/${jobId}`),
    enabled: !!jobId,
    refetchInterval: (query) =>
      ["COMPLETED", "FAILED"].includes(query.state.data?.status ?? "")
        ? false
        : 2000,
  });
  async function create() {
    setBusy(true);
    setError(null);
    try {
      const result = await post<ExportJob>(`/runs/${runId}/exports`, {
        profile,
        safe_spreadsheet: true,
      });
      setJobId(result.id);
      localStorage.setItem(key, result.id);
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  }
  async function download(manifest = false) {
    setBusy(true);
    setError(null);
    try {
      await downloadAuthenticated(
        `/exports/${jobId}/${manifest ? "manifest" : "download"}`,
        manifest ? "manifest.json" : (job.data?.filename ?? "geopol.csv"),
      );
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  }
  const processing =
    !!jobId && !["COMPLETED", "FAILED"].includes(job.data?.status ?? "");
  return (
    <section className="panel form-panel">
      <div className="panel-heading">
        <div>
          <h2>Archivo de salida</h2>
          <p>Incluye los casos sin resolver, con sus coordenadas vacías.</p>
        </div>
        <FileCheck2 size={23} className="teal" aria-hidden="true" />
      </div>
      <div className="export-controls">
        <label>
          Perfil de exportación
          <select value={profile} onChange={(e) => setProfile(e.target.value)}>
            <option value="locations">
              Ubicaciones · sin columnas personales de origen
            </option>
            {["admin", "operator"].includes(user?.role ?? "") && (
              <option value="source_rows">
                Filas originales y resultados · acceso restringido
              </option>
            )}
          </select>
        </label>
        <button
          className="button primary"
          onClick={() => void create()}
          disabled={busy || processing}
        >
          <Download size={17} aria-hidden="true" />
          {processing ? "Preparando archivo…" : "Preparar exportación"}
        </button>
      </div>
      <ErrorNotice error={error || job.error || job.data?.error} />
      {job.data && (
        <div className="export-status">
          <span role="status">
            Exportación: <strong>{label(job.data.status)}</strong>
            {job.data.row_count !== undefined &&
              ` · ${number(job.data.row_count)} filas`}
          </span>
          {job.data.status === "COMPLETED" && (
            <div className="button-row">
              <button
                className="button secondary"
                onClick={() => void download()}
                disabled={busy}
              >
                Descargar CSV
              </button>
              <button
                className="button secondary"
                onClick={() => void download(true)}
                disabled={busy}
              >
                Descargar manifiesto
              </button>
            </div>
          )}
        </div>
      )}
      <details>
        <summary>Contenido y trazabilidad de la descarga</summary>
        <p>
          El CSV está protegido para abrirlo en hojas de cálculo. El manifiesto
          conserva la configuración y las huellas de integridad de la
          exportación.
        </p>
      </details>
    </section>
  );
}
