import { useState, type FormEvent } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { CheckCircle2, ChevronDown, FileSpreadsheet } from "lucide-react";
import { useAuth } from "../auth";
import { post } from "../lib/api";
import { clearResume, getResume, uploadFile } from "../lib/upload";
import { number } from "../lib/format";
import type { Profile, Reference, ReferenceExcelKind, Upload } from "../types";
import { ErrorNotice, Notice } from "./ui";

export const referenceSlots: {
  kind: ReferenceExcelKind;
  title: string;
  description: string;
  kinds: string[];
}[] = [
  {
    kind: "doors",
    title: "Puertas / viviendas",
    description: "Pre Censos · puntos de puerta y dirección.",
    kinds: ["door"],
  },
  {
    kind: "roads",
    title: "Vías y cuadras",
    description: "Pre Censos · líneas, tramos e intersecciones.",
    kinds: ["street", "block", "intersection"],
  },
  {
    kind: "centers",
    title: "Centros poblados",
    description: "Pre Censos · puntos y nombres de centros poblados.",
    kinds: ["nucleus"],
  },
  {
    kind: "boundaries",
    title: "Límites administrativos",
    description: "Pre Censos · distritos, provincias y departamentos.",
    kinds: ["boundary"],
  },
  {
    kind: "jurisdictions",
    title: "Jurisdicciones",
    description: "SIDPOL / DATACRIM · polígonos de jurisdicción.",
    kinds: ["jurisdiction"],
  },
];
const fieldLabels: [string, string][] = [
  ["id", "Identificador"],
  ["ubigeo", "UBIGEO"],
  ["name", "Nombre de referencia"],
  ["street_type", "Tipo de vía"],
  ["street_name", "Nombre de vía"],
  ["door_number", "Número de puerta"],
  ["door_letter", "Letra de puerta"],
  ["block_number", "Cuadra"],
  ["cross_street", "Vía de intersección"],
  ["urban_core", "Núcleo urbano"],
  ["center_code", "Código de centro poblado"],
  ["center_name", "Nombre de centro poblado"],
  ["latitude", "Latitud"],
  ["longitude", "Longitud"],
  ["geometry", "Geometría (GeoJSON o WKT)"],
  ["kind", "Tipo de elemento"],
  ["level", "Nivel territorial"],
  ["connects_at_grade", "Cruce al mismo nivel"],
  ["crs", "Sistema de coordenadas declarado en la fila"],
];
const fieldsByKind: Record<ReferenceExcelKind, string[]> = {
  doors: [
    "id",
    "ubigeo",
    "street_type",
    "street_name",
    "door_number",
    "door_letter",
    "urban_core",
    "latitude",
    "longitude",
    "geometry",
    "crs",
  ],
  roads: [
    "id",
    "ubigeo",
    "street_type",
    "street_name",
    "block_number",
    "cross_street",
    "geometry",
    "kind",
    "connects_at_grade",
    "crs",
  ],
  centers: [
    "id",
    "ubigeo",
    "name",
    "center_code",
    "center_name",
    "urban_core",
    "latitude",
    "longitude",
    "geometry",
    "crs",
  ],
  boundaries: ["id", "ubigeo", "name", "geometry", "level", "crs"],
  jurisdictions: ["id", "ubigeo", "name", "geometry", "crs"],
};
const referenceIssueLabels: Record<string, string> = {
  CRS_NO_CONFIRMADO: "Sistema de coordenadas sin confirmar",
  CRS_DECLARADO_EN_FILA_CONTRADICTORIO:
    "La fila declara otro sistema de coordenadas",
  CAT_VIA_DOMAIN_UNCONFIRMED:
    "Código de tipo de vía sin diccionario confirmado",
  GEOMETRIA_NO_DISPONIBLE: "Falta la geometría o el punto de referencia",
  GEOMETRIA_INVALIDA: "Geometría inválida",
  GEOMETRIA_INCOMPATIBLE_CON_CAPA:
    "La geometría no corresponde a este tipo de referencia",
  LIMITE_NO_DISTRITAL:
    "Límite provincial o departamental; no valida un distrito",
  LIMITE_REQUIERE_UBIGEO_DISTRITAL: "El límite necesita un UBIGEO distrital",
  UBIGEO_DISTRITAL_INVALIDO: "UBIGEO distrital inválido",
  PAR_COORDENADAS_INCOMPLETO: "Falta la latitud o la longitud",
  COORDENADAS_FUERA_DE_RANGO: "Coordenadas fuera de rango",
};
export function ReferenceExcelCards({
  catalogs,
  selected,
  onSelect,
  onBusy,
}: {
  catalogs: Reference[];
  selected: Partial<Record<ReferenceExcelKind, string>>;
  onSelect: (kind: ReferenceExcelKind, id: string) => void;
  onBusy: (kind: ReferenceExcelKind, busy: boolean) => void;
}) {
  const [expanded, setExpanded] = useState<ReferenceExcelKind | null>(null);
  const selectedCount = referenceSlots.filter((slot) =>
    catalogs.some((catalog) => catalog.id === selected[slot.kind]),
  ).length;
  return (
    <section
      className="reference-upload-column"
      aria-label="Cinco archivos de referencia"
    >
      <div className="reference-upload-heading">
        <div className="intake-section-heading">
          <h2>Referencias en Excel</h2>
          <span className="reference-selection-count" role="status">
            {selectedCount} de 5 seleccionadas
          </span>
        </div>
        <p>
          Abre un tipo de referencia para adjuntar un Excel o reutilizar un
          catálogo guardado.
        </p>
      </div>
      <div className="panel reference-list">
        {referenceSlots.map((slot) => (
          <ReferenceExcelCard
            key={slot.kind}
            slot={slot}
            catalogs={catalogs}
            selected={selected[slot.kind] ?? ""}
            expanded={expanded === slot.kind}
            onToggle={() =>
              setExpanded((current) =>
                current === slot.kind ? null : slot.kind,
              )
            }
            onSelect={(id) => onSelect(slot.kind, id)}
            onBusy={(busy) => onBusy(slot.kind, busy)}
          />
        ))}
      </div>
    </section>
  );
}
function ReferenceExcelCard({
  slot,
  catalogs,
  selected,
  expanded,
  onToggle,
  onSelect,
  onBusy,
}: {
  slot: (typeof referenceSlots)[number];
  catalogs: Reference[];
  selected: string;
  expanded: boolean;
  onToggle: () => void;
  onSelect: (id: string) => void;
  onBusy: (busy: boolean) => void;
}) {
  const { user } = useAuth();
  const client = useQueryClient();
  const [file, setFile] = useState<File | null>(null);
  const [upload, setUpload] = useState<Upload | null>(null);
  const [profile, setProfile] = useState<Profile | null>(null);
  const [mapping, setMapping] = useState<Record<string, string>>({});
  const [name, setName] = useState("");
  const [source, setSource] = useState(
    slot.kind === "jurisdictions" ? "SIDPOL / DATACRIM" : "Pre Censos",
  );
  const [version, setVersion] = useState("");
  const [crs, setCrs] = useState("");
  const [evidence, setEvidence] = useState("");
  const [streetTypes, setStreetTypes] = useState<
    { code: string; name: string }[]
  >([]);
  const [busy, setBusy] = useState(false);
  const [offset, setOffset] = useState(0);
  const [error, setError] = useState<unknown>();
  const scope = `reference.${slot.kind}`;
  const saved = getResume(user!.id, scope);
  const choices = catalogs.filter(
    (catalog) =>
      catalog.config?.reference_excel?.kind === slot.kind ||
      (!catalog.config?.reference_excel &&
        catalog.kinds?.some((kind) => slot.kinds.includes(kind))),
  );
  const active = choices.find((catalog) => catalog.id === selected);
  const stagedRows = active?.config?.reference_excel?.staged_rows ?? 0;
  const draft = !!file || !!profile || !!saved;
  const status = busy
    ? "Procesando…"
    : error
      ? "Revisar error"
      : draft
        ? "Importación sin guardar"
        : active
          ? stagedRows
            ? "Con filas pendientes"
            : active.feature_count
              ? "Seleccionada"
              : "Sin elementos disponibles"
          : "Sin seleccionar";
  const detail = busy
    ? (file?.name ?? upload?.filename ?? "Preparando referencia")
    : draft
      ? (file?.name ?? upload?.filename ?? saved?.filename)
      : active
        ? `${active.name} · ${active.version}`
        : slot.description;
  function pending(value: boolean) {
    setBusy(value);
    onBusy(value);
  }
  async function preview(uploadId: string, sheet?: string) {
    const result = await post<Profile>("/reference-excels/preview", {
      upload_id: uploadId,
      kind: slot.kind,
      ...(sheet ? { sheet } : {}),
    });
    setProfile(result);
    setMapping(result.suggested_mapping ?? {});
  }
  async function load(event: FormEvent) {
    event.preventDefault();
    if (!file) return;
    pending(true);
    setError(null);
    try {
      const result = await uploadFile(
        file,
        user!.id,
        setOffset,
        undefined,
        scope,
      );
      setUpload(result);
      setName(file.name.replace(/\.[^.]+$/, ""));
      await preview(result.id);
    } catch (e) {
      setError(e);
    } finally {
      pending(false);
    }
  }
  async function changeSheet(sheet: string) {
    if (!upload) return;
    pending(true);
    setError(null);
    try {
      await preview(upload.id, sheet);
    } catch (e) {
      setError(e);
    } finally {
      pending(false);
    }
  }
  async function importCatalog(event: FormEvent) {
    event.preventDefault();
    if (!upload || !profile) return;
    pending(true);
    setError(null);
    try {
      let codes: Record<string, string> | undefined;
      if (streetTypes.length) {
        if (
          streetTypes.some((entry) => !entry.code.trim() || !entry.name.trim())
        )
          throw new Error(
            "Completa el código y el tipo de vía de cada fila del diccionario, o elimina las filas vacías.",
          );
        if (
          new Set(streetTypes.map((entry) => entry.code.trim())).size !==
          streetTypes.length
        )
          throw new Error(
            "Un código de vía no puede aparecer dos veces en el diccionario.",
          );
        codes = Object.fromEntries(
          streetTypes.map((entry) => [entry.code.trim(), entry.name.trim()]),
        );
      }
      const catalog = await post<Reference>("/reference-excels", {
        upload_id: upload.id,
        kind: slot.kind,
        sheet: profile.sheet || undefined,
        name: name.trim(),
        source: source.trim(),
        version: version.trim(),
        mapping: Object.fromEntries(
          Object.entries(mapping).filter(([, value]) => value),
        ),
        crs: crs || null,
        crs_evidence: crs ? evidence.trim() : null,
        ...(codes ? { street_types: codes } : {}),
      });
      client.setQueryData<{ items: Reference[]; total: number }>(
        ["references"],
        (old) =>
          old
            ? {
                ...old,
                items: [
                  ...old.items.filter((item) => item.id !== catalog.id),
                  catalog,
                ],
                total: old.total + 1,
              }
            : { items: [catalog], total: 1 },
      );
      onSelect(catalog.id);
      clearResume(scope);
      setUpload(null);
      setProfile(null);
      setFile(null);
      void client.invalidateQueries({ queryKey: ["references"] });
    } catch (e) {
      setError(e);
    } finally {
      pending(false);
    }
  }
  return (
    <article
      className={`reference-slot ${active ? "has-reference" : ""} ${expanded ? "is-expanded" : ""}`}
    >
      <h3 className="reference-slot-heading">
        <button
          type="button"
          className="reference-slot-toggle"
          aria-label={`Configurar referencia: ${slot.title}`}
          aria-expanded={expanded}
          aria-controls={`reference-${slot.kind}-editor`}
          aria-describedby={`reference-${slot.kind}-status`}
          onClick={onToggle}
        >
          <FileSpreadsheet size={20} aria-hidden="true" />
          <span className="reference-slot-copy">
            <span className="reference-slot-name">{slot.title}</span>
            <span className="reference-slot-description">{detail}</span>
            {active && (draft || busy || !!error) && (
              <span className="reference-slot-description">
                Se utilizará: {active.name} · {active.version}
              </span>
            )}
          </span>
          <span
            id={`reference-${slot.kind}-status`}
            className={`reference-slot-status ${error ? "has-error" : stagedRows || draft ? "needs-attention" : ""}`}
          >
            {active &&
              !busy &&
              !draft &&
              !error &&
              !stagedRows &&
              !!active.feature_count && (
                <CheckCircle2 size={15} aria-hidden="true" />
              )}
            {status}
          </span>
          <ChevronDown
            size={18}
            className="reference-slot-chevron"
            aria-hidden="true"
          />
        </button>
      </h3>
      <span
        className="sr-only"
        role="status"
        aria-label={`Importación de ${slot.title}`}
        aria-atomic="true"
      >
        {!expanded && (busy || !!error)
          ? `${slot.title}: ${status}. Abre la fuente para ver el detalle.`
          : ""}
      </span>
      <div
        className="reference-slot-editor"
        id={`reference-${slot.kind}-editor`}
        hidden={!expanded}
      >
        {choices.length > 0 && (
          <label className="reference-catalog-choice">
            Catálogo guardado
            <select
              aria-label={`Catálogo guardado · ${slot.title}`}
              value={selected}
              onChange={(e) => onSelect(e.target.value)}
              disabled={busy}
            >
              <option value="">Seleccionar catálogo…</option>
              {choices.map((catalog) => (
                <option key={catalog.id} value={catalog.id}>
                  {catalog.name} · {catalog.version}
                </option>
              ))}
            </select>
          </label>
        )}
        {active && (
          <p
            className="field-hint"
            role="status"
            aria-label="Disponibilidad de la referencia"
          >
            {number(active.feature_count)} elementos disponibles
            {active.config?.reference_excel
              ? ` · ${number(active.config.reference_excel.staged_rows)} filas pendientes de datos o geometría`
              : ""}
            .
          </p>
        )}
        {!!active?.config?.reference_excel?.staged_rows && (
          <details>
            <summary>Motivos de las filas pendientes</summary>
            <ul className="reference-issues">
              {Object.entries(
                active.config.reference_excel.issue_counts ?? {},
              ).map(([code, count]) => (
                <li key={code}>
                  {referenceIssueLabels[code] ??
                    code.replaceAll("_", " ").toLowerCase()}
                  : <strong>{number(count)}</strong>
                </li>
              ))}
            </ul>
            <p>
              Una fila puede tener varios motivos. Corrige o completa la fuente
              y carga una nueva versión para habilitarla.
            </p>
          </details>
        )}
        <section
          className="reference-import"
          aria-label={`Importar Excel · ${slot.title}`}
        >
          <ErrorNotice error={error} />
          {!profile ? (
            <form onSubmit={load} className="reference-file-form">
              <div className="excel-file-field">
                <label
                  className="sr-only"
                  htmlFor={`reference-${slot.kind}-file`}
                >
                  Archivo Excel · {slot.title}
                </label>
                <div className="excel-file-picker">
                  <div
                    className={`excel-file-control ${busy ? "is-disabled" : ""}`}
                  >
                    <span className="excel-file-button" aria-hidden="true">
                      <FileSpreadsheet size={21} strokeWidth={1.8} />
                      {file ? "Cambiar Excel" : "Adjuntar Excel"}
                    </span>
                    <input
                      id={`reference-${slot.kind}-file`}
                      className="excel-file-input"
                      type="file"
                      accept=".xlsx"
                      aria-describedby={`reference-${slot.kind}-file-hint`}
                      required
                      disabled={busy}
                      onChange={(e) => {
                        setFile(e.target.files?.[0] ?? null);
                        setOffset(0);
                      }}
                    />
                  </div>
                  <div
                    className="excel-file-summary"
                    aria-live="polite"
                    aria-atomic="true"
                  >
                    <span className="excel-file-name">
                      {file?.name ??
                        (saved
                          ? "Vuelve a adjuntar el archivo pendiente"
                          : "Archivo .xlsx")}
                    </span>
                    <span
                      className="excel-file-hint"
                      id={`reference-${slot.kind}-file-hint`}
                    >
                      {file
                        ? `${number(Math.max(1, Math.ceil(file.size / 1024)))} KB · Excel (.xlsx)`
                        : saved
                          ? "Selecciona el mismo Excel para reanudar."
                          : "Al guardar, podrás reutilizarlo como catálogo."}
                    </span>
                  </div>
                </div>
              </div>
              {busy && (
                <div role="status">
                  <progress value={offset} max={file?.size || 1} /> Preparando
                  columnas…
                </div>
              )}
              {(file || busy) && (
                <button className="button secondary" disabled={!file || busy}>
                  {busy ? "Leyendo archivo…" : "Leer columnas de referencia"}
                </button>
              )}
            </form>
          ) : (
            <form onSubmit={importCatalog} className="stack">
              <label>
                Hoja · {slot.title}
                <select
                  value={profile.sheet ?? profile.sheets[0]}
                  disabled={busy}
                  onChange={(e) => void changeSheet(e.target.value)}
                >
                  {profile.sheets.map((sheet) => (
                    <option key={sheet}>{sheet}</option>
                  ))}
                </select>
              </label>
              <div className="form-grid">
                <label>
                  Nombre del catálogo
                  <input
                    value={name}
                    required
                    maxLength={200}
                    onChange={(e) => setName(e.target.value)}
                  />
                </label>
                <label>
                  Versión de la fuente
                  <input
                    value={version}
                    required
                    maxLength={100}
                    placeholder="Versión o fecha indicada por el proveedor"
                    onChange={(e) => setVersion(e.target.value)}
                  />
                </label>
              </div>
              <label>
                Origen de los datos / institución
                <input
                  value={source}
                  required
                  maxLength={200}
                  onChange={(e) => setSource(e.target.value)}
                />
              </label>
              <details open>
                <summary>Correspondencia de columnas · {slot.title}</summary>
                <div className="form-grid reference-mapping">
                  {fieldLabels
                    .filter(
                      ([key]) =>
                        fieldsByKind[slot.kind].includes(key) || mapping[key],
                    )
                    .map(([key, title]) => (
                      <label key={key}>
                        {title}
                        <select
                          value={mapping[key] ?? ""}
                          onChange={(e) =>
                            setMapping({ ...mapping, [key]: e.target.value })
                          }
                        >
                          <option value="">No disponible</option>
                          {profile.columns.map((column) => (
                            <option key={column}>{column}</option>
                          ))}
                        </select>
                      </label>
                    ))}
                </div>
              </details>
              {profile.warnings?.map((warning, i) => (
                <Notice key={i}>{warning}</Notice>
              ))}
              <label>
                Sistema de coordenadas · {slot.title}
                <select value={crs} onChange={(e) => setCrs(e.target.value)}>
                  <option value="">
                    Sin confirmar · conservar como referencia pendiente
                  </option>
                  <option value="EPSG:4326">
                    WGS84 · EPSG:4326 documentado
                  </option>
                </select>
              </label>
              {crs ? (
                <label>
                  Documento que confirma WGS84 · {slot.title}
                  <textarea
                    required
                    minLength={8}
                    maxLength={500}
                    value={evidence}
                    onChange={(e) => setEvidence(e.target.value)}
                  />
                </label>
              ) : (
                <p className="field-hint">
                  Las filas sin geometría utilizable o sistema documentado se
                  conservarán pendientes; no validan puntos automáticamente.
                </p>
              )}
              {["doors", "roads"].includes(slot.kind) && (
                <details>
                  <summary>
                    Diccionario de categorías de vía (si son códigos)
                  </summary>
                  <p>
                    Completa únicamente los códigos confirmados por el
                    diccionario de la fuente.
                  </p>
                  {streetTypes.map((entry, index) => (
                    <div className="street-type-entry" key={index}>
                      <label>
                        Código {index + 1}
                        <input
                          value={entry.code}
                          maxLength={50}
                          onChange={(e) =>
                            setStreetTypes((current) =>
                              current.map((item, i) =>
                                i === index
                                  ? { ...item, code: e.target.value }
                                  : item,
                              ),
                            )
                          }
                        />
                      </label>
                      <label>
                        Tipo de vía {index + 1}
                        <input
                          value={entry.name}
                          maxLength={100}
                          onChange={(e) =>
                            setStreetTypes((current) =>
                              current.map((item, i) =>
                                i === index
                                  ? { ...item, name: e.target.value }
                                  : item,
                              ),
                            )
                          }
                        />
                      </label>
                      <button
                        type="button"
                        className="button secondary"
                        aria-label={`Eliminar código ${index + 1}`}
                        onClick={() =>
                          setStreetTypes((current) =>
                            current.filter((_, i) => i !== index),
                          )
                        }
                      >
                        Eliminar
                      </button>
                    </div>
                  ))}
                  <button
                    type="button"
                    className="button secondary"
                    onClick={() =>
                      setStreetTypes((current) => [
                        ...current,
                        { code: "", name: "" },
                      ])
                    }
                  >
                    Añadir categoría de vía
                  </button>
                </details>
              )}
              <div className="button-row">
                <button
                  type="button"
                  className="button secondary"
                  disabled={busy}
                  onClick={() => {
                    setProfile(null);
                    setUpload(null);
                  }}
                >
                  Cambiar archivo de referencia
                </button>
                <button
                  className="button primary"
                  disabled={
                    busy ||
                    !name.trim() ||
                    !source.trim() ||
                    !version.trim() ||
                    (!!crs && evidence.trim().length < 8)
                  }
                >
                  {busy
                    ? "Importando referencia…"
                    : "Guardar y utilizar referencia"}
                </button>
              </div>
            </form>
          )}
        </section>
      </div>
    </article>
  );
}
