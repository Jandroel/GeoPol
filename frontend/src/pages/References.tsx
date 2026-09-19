import { useState, type FormEvent } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Database, Plus, Upload } from "lucide-react";
import { useAuth } from "../auth";
import { request } from "../lib/api";
import { number } from "../lib/format";
import type { Page, Reference } from "../types";
import {
  Empty,
  ErrorNotice,
  Loading,
  Notice,
  PageHeader,
  Pagination,
  Success,
} from "../components/ui";
export function References() {
  const { user } = useAuth();
  const client = useQueryClient();
  const [show, setShow] = useState(false);
  const [page, setPage] = useState(1);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>();
  const [success, setSuccess] = useState("");
  const [name, setName] = useState("");
  const [version, setVersion] = useState("");
  const [source, setSource] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const query = useQuery({
    queryKey: ["references", page],
    queryFn: () =>
      request<Page<Reference>>(`/references?page=${page}&page_size=25`),
  });
  async function submit(e: FormEvent) {
    e.preventDefault();
    if (!file) return;
    setBusy(true);
    setError(null);
    try {
      const form = new FormData();
      form.set("name", name);
      form.set("version", version);
      form.set("source", source);
      form.set("file", file);
      await request<Reference>("/references", { method: "POST", body: form });
      await client.invalidateQueries({ queryKey: ["references"] });
      setShow(false);
      setSuccess(
        "Catálogo importado. Ya puedes seleccionarlo al crear un procesamiento.",
      );
      setName("");
      setVersion("");
      setSource("");
      setFile(null);
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  }
  return (
    <>
      <PageHeader
        eyebrow="FUENTES TERRITORIALES"
        title="Catálogos de referencia"
        description="Fuentes versionadas para contrastar direcciones y verificar ubicaciones."
        actions={
          ["admin", "operator"].includes(user?.role ?? "") && (
            <button
              className="button primary"
              onClick={() => {
                setShow(!show);
                setSuccess("");
              }}
            >
              <Plus size={18} aria-hidden="true" />
              {show ? "Cerrar formulario" : "Importar catálogo"}
            </button>
          )
        }
      />
      {success && <Success>{success}</Success>}
      {show && (
        <form className="panel form-panel stack" onSubmit={submit}>
          <h2>Importar referencia</h2>
          <ErrorNotice error={error} />
          <div className="form-grid">
            <label>
              Nombre
              <input
                required
                value={name}
                onChange={(e) => setName(e.target.value)}
              />
            </label>
            <label>
              Versión
              <input
                required
                value={version}
                onChange={(e) => setVersion(e.target.value)}
                placeholder="2026-01"
              />
            </label>
            <label>
              Fuente y procedencia
              <input
                required
                value={source}
                onChange={(e) => setSource(e.target.value)}
                placeholder="Entidad responsable y origen del catálogo"
              />
            </label>
            <label>
              Archivo CSV o GeoJSON
              <input
                type="file"
                accept=".csv,.geojson,.json"
                required
                onChange={(e) => setFile(e.target.files?.[0] ?? null)}
              />
            </label>
          </div>
          <Notice>
            Usa las columnas id, kind, ubigeo, street_type, street_name,
            door_number, block_number, cross_street, name, latitude y longitude.
            En GeoJSON, los atributos corresponden a properties; las geometrías
            se expresan en WGS84.
          </Notice>
          <details>
            <summary>Tipos de referencia admitidos</summary>
            <p>
              door (puerta), block (cuadra), intersection (intersección), site
              (sitio), nucleus (núcleo), jurisdiction (jurisdicción), boundary
              (límite). Las coordenadas deben ser numéricas; boundary requiere
              una geometría Polygon o MultiPolygon en GeoJSON.
            </p>
            <a href="/reference-demo.csv" download className="text-link">
              Descargar catálogo sintético de ejemplo
            </a>
          </details>
          <div>
            <button className="button primary" disabled={busy}>
              <Upload size={17} aria-hidden="true" />
              {busy ? "Importando…" : "Importar y verificar catálogo"}
            </button>
          </div>
        </form>
      )}
      <section className="panel">
        {query.isPending ? (
          <Loading />
        ) : query.isError ? (
          <ErrorNotice error={query.error} />
        ) : (
          <>
            {query.data.items.length ? (
              <div className="reference-grid">
                {query.data.items.map((r) => (
                  <article className="reference-card" key={r.id}>
                    <div className="reference-icon">
                      <Database size={24} aria-hidden="true" />
                    </div>
                    <span className="version-chip">{r.version}</span>
                    <h2>{r.name}</h2>
                    <p>{r.source}</p>
                    <div className="reference-count">
                      <strong>{number(r.feature_count)}</strong> elementos de
                      referencia
                    </div>
                    <details>
                      <summary>Identidad y verificación</summary>
                      <dl>
                        <dt>Identificador</dt>
                        <dd className="mono">{r.id}</dd>
                        <dt>SHA-256</dt>
                        <dd className="mono break-word">{r.sha256}</dd>
                      </dl>
                    </details>
                  </article>
                ))}
              </div>
            ) : (
              <Empty
                title="Aún no hay referencias"
                text="Importa un catálogo documentado para habilitar búsquedas y corroboración territorial."
              />
            )}
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
