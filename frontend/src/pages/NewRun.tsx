import { useState, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { ArrowRight, Check, FileUp, UploadCloud } from "lucide-react";
import { useAuth } from "../auth";
import { post, request } from "../lib/api";
import { clearResume, getResume, uploadFile } from "../lib/upload";
import type { Page, Profile, Reference, Run, Upload } from "../types";
import { ErrorNotice, Notice, PageHeader } from "../components/ui";
const fields: [string, string][] = [
  ["complaint_id", "Identificador de denuncia"],
  ["location_original", "Dirección / lugar del hecho"],
  ["ubigeo", "Código UBIGEO"],
  ["district", "Distrito"],
  ["street_type", "Tipo de vía"],
  ["street_name", "Nombre de vía"],
  ["door_number", "Número de puerta"],
  ["block_number", "Cuadra"],
  ["cross_street", "Vía de intersección"],
  ["site_name", "Sitio de interés"],
  ["urban_core", "Núcleo urbano"],
  ["latitude", "Latitud (xx)"],
  ["longitude", "Longitud (yy)"],
  ["coordinate_origin", "Origen de coordenadas"],
];
export function NewRun() {
  const { user } = useAuth();
  const navigate = useNavigate();
  const [file, setFile] = useState<File | null>(null);
  const [upload, setUpload] = useState<Upload | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>();
  const [offset, setOffset] = useState(0);
  const [name, setName] = useState("");
  const [reference, setReference] = useState("");
  const [sheet, setSheet] = useState("");
  const [mapping, setMapping] = useState<Record<string, string>>({});
  const [delimiter, setDelimiter] = useState(",");
  const [encoding, setEncoding] = useState("utf-8-sig");
  const saved = getResume(user!.id);
  const refs = useQuery({
    queryKey: ["references"],
    queryFn: () => request<Page<Reference>>("/references?page_size=100"),
  });
  function applyProfile(profile?: Profile) {
    if (!profile) return;
    setMapping(profile.suggested_mapping ?? {});
    setSheet(profile.sheet ?? profile.sheets?.[0] ?? "");
    setDelimiter(profile.delimiter ?? ",");
    setEncoding(profile.encoding ?? "utf-8-sig");
  }
  async function updateProfile(changes: {
    sheet?: string;
    delimiter?: string;
    encoding?: string;
  }) {
    if (!upload) return;
    setBusy(true);
    setError(null);
    const parameters = new URLSearchParams({
      ...(sheet ? { sheet } : {}),
      delimiter,
      encoding,
      ...changes,
    });
    try {
      const profile = await request<Profile>(
        `/uploads/${upload.id}/profile?${parameters}`,
      );
      setUpload({ ...upload, profile });
      applyProfile(profile);
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  }
  async function submitUpload(event: FormEvent) {
    event.preventDefault();
    if (!file) return;
    setBusy(true);
    setError(null);
    try {
      const result = await uploadFile(file, user!.id, setOffset);
      setUpload(result);
      applyProfile(result.profile);
      if (!name) setName(file.name.replace(/\.[^.]+$/, ""));
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  }
  async function create(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const run = await post<Run>("/runs", {
        upload_id: upload!.id,
        name,
        sheet: sheet || undefined,
        mapping: Object.fromEntries(
          Object.entries(mapping).filter(([, value]) => value),
        ),
        reference_id: reference || undefined,
        delimiter,
        encoding,
        crs: "EPSG:4326",
      });
      clearResume();
      navigate(`/runs/${run.id}`);
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  }
  return (
    <>
      <PageHeader
        eyebrow="NUEVO PROCESAMIENTO"
        title="Del archivo a la ubicación"
        description="Carga tus datos, verifica las columnas y elige las referencias de trabajo."
      />
      <ol className="steps">
        <li className={upload ? "done" : "current"}>
          <span>{upload ? <Check size={16} aria-hidden="true" /> : "1"}</span>
          Archivo de origen
        </li>
        <li className={upload ? "current" : ""}>
          <span>2</span>Configuración y mapeo
        </li>
        <li>
          <span>3</span>Procesamiento
        </li>
      </ol>
      <ErrorNotice error={error} />
      {!upload ? (
        <form onSubmit={submitUpload} className="panel upload-panel">
          <div className="upload-illustration">
            <UploadCloud size={44} strokeWidth={1.4} aria-hidden="true" />
          </div>
          <h2>Un nuevo punto de partida</h2>
          <p>
            Selecciona un archivo CSV o XLSX. Las filas originales se preservan.
          </p>
          {saved && (
            <Notice>
              Hay una carga pendiente: <strong>{saved.filename}</strong>.
              Selecciona el mismo archivo para reanudar desde el último bloque
              confirmado.
            </Notice>
          )}
          <label className="file-drop" htmlFor="source-file">
            <FileUp size={24} aria-hidden="true" />
            <strong>{file?.name ?? "Seleccionar archivo de origen"}</strong>
            <span>
              {file
                ? `${(file.size / 1024 / 1024).toFixed(2)} MB`
                : "CSV o XLSX · Carga por bloques de hasta 8 MiB"}
            </span>
            <input
              id="source-file"
              type="file"
              accept=".csv,.xlsx"
              disabled={busy}
              required
              onChange={(e) => {
                setFile(e.target.files?.[0] ?? null);
                setOffset(0);
              }}
            />
          </label>
          {busy && (
            <div className="upload-progress">
              <progress max={file?.size || 1} value={offset} />
              <span role="status">
                {file ? Math.floor((offset / file.size) * 100) : 0}% enviado ·
                La carga se puede reanudar si se interrumpe.
              </span>
            </div>
          )}
          <button className="button primary" disabled={!file || busy}>
            {busy ? "Cargando archivo…" : "Cargar y verificar columnas"}
            <ArrowRight size={18} aria-hidden="true" />
          </button>
          <a className="text-link demo-link" href="/demo.csv" download>
            Descargar un ejemplo sintético
          </a>
        </form>
      ) : (
        <form onSubmit={create} className="stack">
          <section className="panel form-panel">
            <div className="panel-heading">
              <div>
                <h2>Configuración del procesamiento</h2>
                <p>{upload.filename} · Archivo recibido y verificado</p>
              </div>
              <Check size={22} className="teal" aria-hidden="true" />
            </div>
            <div className="form-grid">
              <label>
                Nombre del procesamiento
                <input
                  required
                  maxLength={200}
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                />
              </label>
              <label>
                Catálogo de referencia
                <select
                  aria-label="Catálogo de referencia"
                  value={reference}
                  onChange={(e) => setReference(e.target.value)}
                >
                  <option value="">
                    Sin catálogo · se indicará la limitación
                  </option>
                  {refs.data?.items.map((r) => (
                    <option key={r.id} value={r.id}>
                      {r.name} · {r.version}
                    </option>
                  ))}
                </select>
              </label>
              {!!upload.profile?.sheets.length && (
                <label>
                  Hoja de trabajo
                  <select
                    aria-label="Hoja de trabajo"
                    value={sheet}
                    disabled={busy}
                    onChange={(e) =>
                      void updateProfile({ sheet: e.target.value })
                    }
                  >
                    {upload.profile.sheets.map((s) => (
                      <option key={s}>{s}</option>
                    ))}
                  </select>
                </label>
              )}
              {file?.name.toLowerCase().endsWith(".csv") && (
                <>
                  <label>
                    Separador CSV
                    <select
                      aria-label="Separador CSV"
                      value={delimiter}
                      disabled={busy}
                      onChange={(e) =>
                        void updateProfile({ delimiter: e.target.value })
                      }
                    >
                      <option value=",">Coma (,)</option>
                      <option value=";">Punto y coma (;)</option>
                      <option value={"\t"}>Tabulación</option>
                      <option value="|">Barra vertical (|)</option>
                    </select>
                  </label>
                  <label>
                    Codificación
                    <select
                      aria-label="Codificación"
                      value={encoding}
                      disabled={busy}
                      onChange={(e) =>
                        void updateProfile({ encoding: e.target.value })
                      }
                    >
                      <option value="utf-8-sig">UTF-8</option>
                      <option value="cp1252">Windows-1252</option>
                      <option value="latin-1">Latin-1</option>
                    </select>
                  </label>
                </>
              )}
            </div>
            <ErrorNotice error={refs.error} />
            {!reference && (
              <Notice>
                La falta de cartografía se registrará como limitación de
                referencia. No equivale a una búsqueda sin coincidencias.
              </Notice>
            )}
            {upload.profile?.warnings.map((warning, i) => (
              <Notice key={i}>{warning}</Notice>
            ))}
          </section>
          <section className="panel form-panel">
            <div className="panel-heading">
              <div>
                <h2>Correspondencia de columnas</h2>
                <p>
                  Revisa las sugerencias. Las columnas sin correspondencia
                  permanecen en las filas originales.
                </p>
              </div>
            </div>
            <div className="form-grid mapping-grid">
              {fields.map(([key, title]) => (
                <label key={key}>
                  {title}
                  <select
                    aria-label={title}
                    value={mapping[key] ?? ""}
                    onChange={(e) =>
                      setMapping({ ...mapping, [key]: e.target.value })
                    }
                  >
                    <option value="">No disponible en este archivo</option>
                    {upload.profile?.columns.map((column) => (
                      <option key={column} value={column}>
                        {column}
                      </option>
                    ))}
                  </select>
                </label>
              ))}
            </div>
            <Notice>
              Las coordenadas se interpretan como WGS84 (EPSG:4326). En archivos
              SIDPOL: xx = latitud, yy = longitud. Los centroides forzados no se
              consideran coordenadas originales.
            </Notice>
          </section>
          <div className="form-actions">
            <button
              type="button"
              className="button secondary"
              onClick={() => setUpload(null)}
              disabled={busy}
            >
              Cambiar archivo
            </button>
            <button className="button primary" disabled={busy || !name.trim()}>
              {busy ? "Creando procesamiento…" : "Iniciar procesamiento"}
              <ArrowRight size={18} aria-hidden="true" />
            </button>
          </div>
        </form>
      )}
    </>
  );
}
