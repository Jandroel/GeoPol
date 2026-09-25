import {
  createContext,
  useContext,
  useState,
  type FormEvent,
  type ReactNode,
} from "react";
import { Link, useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import {
  ArrowRight,
  Check,
  FileUp,
  FileCheck2,
  FileSpreadsheet,
} from "lucide-react";
import { useAuth } from "../auth";
import { post, request } from "../lib/api";
import { clearResume, getResume, uploadFile } from "../lib/upload";
import type {
  Page,
  ProcessingDefaults,
  Profile,
  Reference,
  ReferenceExcelKind,
  Run,
  Upload,
} from "../types";
import { Empty, ErrorNotice, Notice, PageHeader } from "../components/ui";
import { CoordinatePolicy } from "../components/CoordinatePolicy";
import { ReferenceCapability } from "../components/ReferenceCapability";
import {
  ReferenceExcelCards,
  ReferenceWorkspaceProvider,
} from "../components/ReferenceExcelCards";
import {
  InputValidationPanel,
  type InputValidationReport,
} from "../components/InputValidationPanel";
import "./intake-workspace.css";
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
  ["center_name", "Nombre del centro poblado del hecho"],
  ["center_code", "Código del centro poblado del hecho"],
  ["jurisdiction_name", "Nombre de jurisdicción del hecho"],
  ["jurisdiction_code", "Código de jurisdicción del hecho"],
  ["latitude", "Latitud (xx)"],
  ["longitude", "Longitud (yy)"],
  ["coordinate_origin", "Origen de coordenadas"],
  ["source_quality_flag", "FLAG de origen"],
];
const primaryFields = new Set([
  "complaint_id",
  "location_original",
  "ubigeo",
  "source_quality_flag",
  "latitude",
  "longitude",
]);
function useDraftState() {
  const [file, setFile] = useState<File | null>(null);
  const [upload, setUpload] = useState<Upload | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>();
  const [offset, setOffset] = useState(0);
  const [name, setName] = useState("");
  const [reference, setReference] = useState("default");
  const [referenceSlots, setReferenceSlots] = useState<
    Partial<Record<ReferenceExcelKind, string>>
  >({});
  const [referenceBusy, setReferenceBusy] = useState<
    Partial<Record<ReferenceExcelKind, boolean>>
  >({});
  const [workflow, setWorkflow] = useState("quality_v1");
  const [crsConfirmed, setCrsConfirmed] = useState(false);
  const [crsEvidence, setCrsEvidence] = useState("");
  const [sheet, setSheet] = useState("");
  const [mapping, setMapping] = useState<Record<string, string>>({});
  const [delimiter, setDelimiter] = useState(",");
  const [encoding, setEncoding] = useState("utf-8-sig");
  return {
    file,
    setFile,
    upload,
    setUpload,
    busy,
    setBusy,
    error,
    setError,
    offset,
    setOffset,
    name,
    setName,
    reference,
    setReference,
    referenceSlots,
    setReferenceSlots,
    referenceBusy,
    setReferenceBusy,
    workflow,
    setWorkflow,
    crsConfirmed,
    setCrsConfirmed,
    crsEvidence,
    setCrsEvidence,
    sheet,
    setSheet,
    mapping,
    setMapping,
    delimiter,
    setDelimiter,
    encoding,
    setEncoding,
  };
}
const UploadWorkspace = createContext<ReturnType<typeof useDraftState> | null>(
  null,
);
export function UploadWorkspaceProvider({ children }: { children: ReactNode }) {
  const value = useDraftState();
  return (
    <UploadWorkspace.Provider value={value}>
      <ReferenceWorkspaceProvider>{children}</ReferenceWorkspaceProvider>
    </UploadWorkspace.Provider>
  );
}
type IntakeMode = "overview" | "validation" | "legacy";
export function NewRun({ mode = "legacy" }: { mode?: IntakeMode }) {
  const draft = useContext(UploadWorkspace);
  if (!draft)
    return (
      <UploadWorkspaceProvider>
        <NewRun mode={mode} />
      </UploadWorkspaceProvider>
    );
  return <NewRunForm mode={mode} draft={draft} />;
}
function NewRunForm({
  mode,
  draft,
}: {
  mode: IntakeMode;
  draft: ReturnType<typeof useDraftState>;
}) {
  const { user } = useAuth();
  const navigate = useNavigate();
  const {
    file,
    setFile,
    upload,
    setUpload,
    busy,
    setBusy,
    error,
    setError,
    offset,
    setOffset,
    name,
    setName,
    reference,
    setReference,
    referenceSlots,
    setReferenceSlots,
    referenceBusy,
    setReferenceBusy,
    workflow,
    setWorkflow,
    crsConfirmed,
    setCrsConfirmed,
    crsEvidence,
    setCrsEvidence,
    sheet,
    setSheet,
    mapping,
    setMapping,
    delimiter,
    setDelimiter,
    encoding,
    setEncoding,
  } = draft;
  const referenceIds = [
    ...new Set(Object.values(referenceSlots).filter(Boolean)),
  ];
  const importingReference = Object.values(referenceBusy).some(Boolean);
  const validation = useQuery({
    queryKey: [
      "input-validation",
      upload?.id,
      sheet,
      mapping,
      delimiter,
      encoding,
    ],
    queryFn: () =>
      post<InputValidationReport>(`/uploads/${upload!.id}/validation`, {
        sheet: sheet || undefined,
        mapping: Object.fromEntries(
          Object.entries(mapping).filter(([, value]) => value),
        ),
        delimiter,
        encoding,
      }),
    enabled: mode === "validation" && !!upload,
    staleTime: 60_000,
    retry: false,
  });
  const saved = getResume(user!.id);
  const refs = useQuery({
    queryKey: ["references"],
    queryFn: () => request<Page<Reference>>("/references?page_size=100"),
  });
  const defaults = useQuery({
    queryKey: ["processing-defaults"],
    queryFn: () => request<ProcessingDefaults>("/processing-defaults"),
  });
  const selectedCatalog =
    reference === "default"
      ? defaults.data?.catalog
      : refs.data?.items.find((r) => r.id === reference);
  const defaultUnavailable =
    !referenceIds.length &&
    reference === "default" &&
    defaults.data?.status !== "ready";
  function mappingControl([key, title]: [string, string]) {
    return (
      <label key={key}>
        {title}
        <select
          aria-label={title}
          value={mapping[key] ?? ""}
          disabled={busy}
          onChange={(e) => setMapping({ ...mapping, [key]: e.target.value })}
        >
          <option value="">No disponible en este archivo</option>
          {upload?.profile?.columns.map((column) => (
            <option key={column} value={column}>
              {column}
            </option>
          ))}
        </select>
      </label>
    );
  }
  function applyProfile(profile?: Profile) {
    if (!profile) return;
    setMapping(profile.suggested_mapping ?? {});
    setSheet(profile.sheet ?? profile.sheets?.[0] ?? "");
    setDelimiter(profile.delimiter ?? ",");
    setEncoding(profile.encoding ?? "utf-8-sig");
  }
  function resetSource() {
    setUpload(null);
    setFile(null);
    setName("");
    setMapping({});
    setSheet("");
    setCrsConfirmed(false);
    setCrsEvidence("");
    setError(null);
    setOffset(0);
  }
  function selectSourceFile(next?: File) {
    if (!next) return;
    if (upload) resetSource();
    setFile(next);
    setOffset(0);
    setCrsConfirmed(false);
    setCrsEvidence("");
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
      if (mode === "overview") navigate("/validation");
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
        workflow,
        ...(referenceIds.length
          ? { reference_ids: referenceIds, reference_id: null }
          : reference === "default"
            ? {}
            : { reference_id: reference || null }),
        delimiter,
        encoding,
        crs: crsConfirmed ? "EPSG:4326" : null,
        crs_evidence: crsConfirmed ? crsEvidence.trim() : null,
      });
      clearResume();
      resetSource();
      navigate(
        mode === "legacy"
          ? `/runs/${run.id}${workflow === "quality_v1" ? "?tab=quality" : ""}`
          : `/procedures?run_id=${run.id}`,
      );
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  }
  if (mode === "validation" && !upload)
    return (
      <>
        <PageHeader
          title="Validación"
          description="Comprueba las columnas y los flags del archivo antes de iniciar los procedimientos."
        />
        <Empty
          title="Primero carga el archivo de SIDPOL"
          text={
            saved
              ? `Hay una carga guardada de ${saved.filename}. Vuelve a elegir el mismo archivo en Vista general para continuar.`
              : "En Vista general puedes adjuntar el Excel de la PNP y elegir las referencias censales."
          }
          action={
            <Link className="button primary" to="/">
              Ir a carga de archivos <ArrowRight size={18} aria-hidden="true" />
            </Link>
          }
        />
      </>
    );
  return (
    <div className={`intake-workspace intake-${mode}`}>
      {mode !== "overview" && (
        <PageHeader
          title={mode === "validation" ? "Validación" : "Carga de archivos"}
          description={
            mode === "validation"
              ? "Comprueba el archivo, sus columnas y los flags antes de ejecutar los procedimientos."
              : "Carga el Excel de la PNP y selecciona las fuentes con las que se contrastarán sus direcciones."
          }
        />
      )}
      {mode !== "overview" && (
        <ol className="steps">
          <li className={upload ? "done" : "current"}>
            <span>{upload ? <Check size={16} aria-hidden="true" /> : "1"}</span>
            Archivo de origen
          </li>
          <li className={upload ? "current" : ""}>
            <span>2</span>Validación y mapeo
          </li>
          <li>
            <span>3</span>Procesamiento
          </li>
        </ol>
      )}
      <ErrorNotice error={error} />
      <div className="intake-grid">
        <div className="intake-source">
          <div className="intake-source-heading">
            <div className="intake-section-heading">
              <h2>
                {mode === "overview"
                  ? "SIDPOL / DATACRIM"
                  : "Archivo de la PNP"}
              </h2>
              <span className="intake-source-label">
                {upload ? "Archivo cargado" : "Archivo de origen"}
              </span>
            </div>
            <p>
              {mode === "overview"
                ? "Archivo de hechos delictivos de la PNP."
                : "Las filas originales se conservarán con cada resultado."}
            </p>
          </div>
          {!upload ? (
            <form onSubmit={submitUpload} className="panel upload-panel">
              {saved && (
                <Notice>
                  Hay una carga pendiente: <strong>{saved.filename}</strong>.
                  Selecciona el mismo archivo para reanudar desde el último
                  bloque confirmado.
                </Notice>
              )}
              {mode === "overview" && (
                <div className="source-file-summary">
                  <FileSpreadsheet
                    size={32}
                    strokeWidth={1.6}
                    aria-hidden="true"
                  />
                  <div>
                    <strong>{file?.name ?? "Ningún archivo adjunto"}</strong>
                    <span>
                      {file
                        ? `${(file.size / 1024 / 1024).toFixed(2)} MB · Listo para cargar`
                        : "Selecciona el archivo que quieres validar."}
                    </span>
                  </div>
                </div>
              )}
              <label
                className={
                  mode === "overview" ? "source-excel-picker" : "file-drop"
                }
                htmlFor="source-file"
              >
                {mode === "overview" ? (
                  <>
                    <FileSpreadsheet size={18} aria-hidden="true" />
                    <span>{file ? "Cambiar Excel" : "Adjuntar Excel"}</span>
                  </>
                ) : (
                  <>
                    <span className="source-file-icon">
                      <FileUp size={28} strokeWidth={1.6} aria-hidden="true" />
                    </span>
                    <strong>
                      {file?.name ?? "Seleccionar archivo de origen"}
                    </strong>
                    <span>
                      {file
                        ? `${(file.size / 1024 / 1024).toFixed(2)} MB`
                        : "Excel (.xlsx) · también compatible con CSV"}
                    </span>
                  </>
                )}
                <input
                  id="source-file"
                  type="file"
                  aria-label="Archivo SIDPOL / DATACRIM"
                  accept=".csv,.xlsx"
                  disabled={busy}
                  required={!file}
                  onChange={(e) => {
                    selectSourceFile(e.target.files?.[0]);
                  }}
                />
              </label>
              {mode === "overview" && (
                <p className="source-format">
                  Excel (.xlsx) · también compatible con CSV
                </p>
              )}
              {busy && (
                <div className="upload-progress">
                  <progress max={file?.size || 1} value={offset} />
                  <span role="status">
                    {file ? Math.floor((offset / file.size) * 100) : 0}% enviado
                    · La carga se puede reanudar si se interrumpe.
                  </span>
                </div>
              )}
              <div className="source-upload-actions">
                <button
                  className="button primary"
                  disabled={!file || busy || importingReference}
                >
                  {busy
                    ? "Cargando archivo…"
                    : mode === "overview"
                      ? "Continuar validación"
                      : "Cargar y verificar columnas"}
                  <ArrowRight size={18} aria-hidden="true" />
                </button>
              </div>
            </form>
          ) : mode === "overview" ? (
            <section className="panel loaded-source">
              <FileCheck2 size={28} aria-hidden="true" />
              <div>
                <strong>{upload.filename}</strong>
                <p>
                  Archivo cargado. Continúa con la comprobación de columnas y
                  flags.
                </p>
              </div>
              <label className="source-excel-picker" htmlFor="source-file">
                <FileSpreadsheet size={18} aria-hidden="true" /> Cambiar Excel
                <input
                  id="source-file"
                  type="file"
                  aria-label="Archivo SIDPOL / DATACRIM"
                  accept=".csv,.xlsx"
                  disabled={busy}
                  onChange={(event) =>
                    selectSourceFile(event.target.files?.[0])
                  }
                />
              </label>
              <Link className="button primary" to="/validation">
                Continuar validación <ArrowRight size={18} aria-hidden="true" />
              </Link>
            </section>
          ) : (
            <form onSubmit={create} className="stack">
              {mode === "validation" && (
                <InputValidationPanel
                  report={validation.data}
                  pending={validation.isFetching}
                  error={validation.error}
                />
              )}
              <section className="panel form-panel">
                <div className="panel-heading">
                  <div>
                    <h2>Archivo y referencias</h2>
                    <p>{upload.filename}</p>
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
                      disabled={
                        busy ||
                        !!referenceIds.length ||
                        defaults.isPending ||
                        refs.isPending
                      }
                      onChange={(e) => setReference(e.target.value)}
                    >
                      <option value="default">
                        {defaults.data?.status === "ready"
                          ? `Referencia base · ${defaults.data.catalog?.name}`
                          : "Referencia base no disponible"}
                      </option>
                      <option value="">
                        Procesar explícitamente sin catálogo
                      </option>
                      {refs.data?.items.map((r) => (
                        <option key={r.id} value={r.id}>
                          {r.name} · {r.version}
                        </option>
                      ))}
                    </select>
                  </label>
                  <label>
                    Flujo de procesamiento
                    <select
                      value={workflow}
                      onChange={(e) => setWorkflow(e.target.value)}
                    >
                      <option value="quality_v1">
                        Por calidad · puertas primero
                      </option>
                      <option value="legacy">Flujo general anterior</option>
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
                <ErrorNotice error={refs.error || defaults.error} />
                {!!referenceIds.length && (
                  <Notice>
                    Se utilizarán {referenceIds.length} fuentes seleccionadas.
                    Las fuentes pendientes se mostrarán como limitaciones de
                    cobertura.
                  </Notice>
                )}
                {!referenceIds.length && selectedCatalog && (
                  <ReferenceCapability catalog={selectedCatalog} />
                )}
                {defaultUnavailable && (
                  <Notice>
                    No hay una referencia base disponible. Configúrala en
                    Catálogos de referencia, selecciona otra fuente o elige
                    explícitamente procesar sin catálogo.
                  </Notice>
                )}
                {!reference && !referenceIds.length && (
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
                  {fields
                    .filter(
                      ([key]) =>
                        mode !== "validation" || primaryFields.has(key),
                    )
                    .map(mappingControl)}
                </div>
                {mode === "validation" && (
                  <details className="validation-extra-fields">
                    <summary>Campos complementarios de la dirección</summary>
                    <div className="form-grid mapping-grid">
                      {fields
                        .filter(([key]) => !primaryFields.has(key))
                        .map(mappingControl)}
                    </div>
                  </details>
                )}
                <CoordinatePolicy
                  confirmed={crsConfirmed}
                  evidence={crsEvidence}
                  onConfirmed={setCrsConfirmed}
                  onEvidence={setCrsEvidence}
                  disabled={busy}
                />
              </section>
              <div className="form-actions">
                <button
                  type="button"
                  className="button secondary"
                  onClick={resetSource}
                  disabled={busy}
                >
                  Cambiar archivo
                </button>
                <button
                  className="button primary"
                  disabled={
                    busy ||
                    importingReference ||
                    !name.trim() ||
                    defaults.isPending ||
                    refs.isPending ||
                    defaultUnavailable ||
                    (crsConfirmed && crsEvidence.trim().length < 8) ||
                    (mode === "validation" &&
                      (!validation.data?.ready ||
                        validation.isFetching ||
                        validation.isError))
                  }
                >
                  {busy ? "Creando procesamiento…" : "Iniciar procesamiento"}
                  <ArrowRight size={18} aria-hidden="true" />
                </button>
              </div>
            </form>
          )}
        </div>
        {mode === "validation" && upload ? (
          <aside className="validation-reference-summary panel">
            <h2>Referencias de contraste</h2>
            {referenceIds.length ? (
              <ul>
                {referenceIds.map((id) => {
                  const catalog = refs.data?.items.find(
                    (item) => item.id === id,
                  );
                  return (
                    <li key={id}>
                      <strong>
                        {catalog?.name ?? "Referencia seleccionada"}
                      </strong>
                      <span>{catalog?.version}</span>
                    </li>
                  );
                })}
              </ul>
            ) : (
              <p>
                {selectedCatalog
                  ? `${selectedCatalog.name} · ${selectedCatalog.version}`
                  : "Selecciona una referencia o confirma el procesamiento sin catálogo."}
              </p>
            )}
            <Link className="button secondary" to="/">
              Cambiar referencias
            </Link>
          </aside>
        ) : (
          <ReferenceExcelCards
            editorMode={mode === "overview" ? "dialog" : "inline"}
            catalogs={refs.data?.items ?? []}
            selected={referenceSlots}
            onSelect={(kind, id) =>
              setReferenceSlots((current) => ({ ...current, [kind]: id }))
            }
            onBusy={(kind, pending) =>
              setReferenceBusy((current) => ({ ...current, [kind]: pending }))
            }
          />
        )}
      </div>
    </div>
  );
}
