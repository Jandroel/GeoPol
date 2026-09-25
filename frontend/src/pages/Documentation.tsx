import { useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";
import {
  BookOpen,
  ChevronDown,
  ChevronRight,
  FileSpreadsheet,
  Library,
  ListChecks,
  Search,
  SlidersHorizontal,
  Upload,
  X,
} from "lucide-react";
import { Empty, PageHeader } from "../components/ui";
import "./documentation.css";

interface Guide {
  id: string;
  title: string;
  category: string;
  summary: string;
  source: string;
  sections: { title: string; paragraphs?: string[]; steps?: string[] }[];
}
const categories = [
  { id: "all", label: "Todos los documentos", icon: Library, tone: "cyan" },
  { id: "general", label: "General", icon: BookOpen, tone: "cyan" },
  {
    id: "procedures",
    label: "Procedimientos",
    icon: ListChecks,
    tone: "indigo",
  },
  { id: "usage", label: "Guías de uso", icon: Upload, tone: "teal" },
  {
    id: "review",
    label: "Correcciones manuales",
    icon: SlidersHorizontal,
    tone: "amber",
  },
  {
    id: "formats",
    label: "Formatos y exportaciones",
    icon: FileSpreadsheet,
    tone: "rose",
  },
];
const guides: Guide[] = [
  {
    id: "methodology",
    title: "Metodología general",
    category: "general",
    summary: "Flujo de trabajo, evidencia y límites de la geocodificación.",
    source: "docs/quality-workflow.md · docs/limitations.md",
    sections: [
      {
        title: "Objetivo",
        paragraphs: [
          "GeoPol conserva el archivo recibido, normaliza las ubicaciones, las contrasta con referencias documentadas y permite revisar las excepciones. Una dirección legible o un flag de calidad no son suficientes para verificar su ubicación.",
        ],
      },
      {
        title: "Recorrido de trabajo",
        steps: [
          "Vista general: adjuntar el archivo SIDPOL/PNP y seleccionar o importar referencias.",
          "Validación: revisar columnas, hoja y configuración; confirmar el sistema de coordenadas solo con evidencia del proveedor.",
          "Procedimientos: consultar la actividad y continuar las etapas que ofrece el servidor.",
          "Estadística: consultar cantidades, estados, flags y exportaciones.",
          "Documentación: consultar estas guías y las reglas vigentes.",
        ],
      },
      {
        title: "Condiciones de confianza",
        paragraphs: [
          "Cada resultado conserva método, procedencia, precisión, evidencia e historial. Las áreas y los tramos mantienen su geometría: no se les asigna una puerta ni un centroide inventado.",
          "La cobertura depende de las referencias realmente disponibles. La falta de una capa se distingue de una búsqueda terminada sin coincidencias. Las guías describen esta aplicación; no constituyen normativa oficial del INEI.",
        ],
      },
    ],
  },
  {
    id: "normalization",
    title: "1. Normalización",
    category: "procedures",
    summary:
      "Preparación de los componentes sin perder la información original.",
    source: "docs/quality-workflow.md · docs/review-workflow.md",
    sections: [
      {
        title: "Qué hace",
        paragraphs: [
          "Estandariza los campos reconocidos y separa componentes como vía, puerta, cuadra, distrito y coordenadas. Conserva el valor original y registra las transformaciones para su consulta.",
        ],
      },
      {
        title: "Qué revisar",
        steps: [
          "Comprobar que la columna de dirección y el identificador correspondan al archivo recibido.",
          "Conservar UBIGEO e identificadores con sus ceros iniciales.",
          "Consultar los avisos de ambigüedad y los campos normalizados de una ficha cuando sea necesario.",
        ],
      },
      {
        title: "Alcance",
        paragraphs: [
          "Normalizar no prueba que la dirección exista. S/N no se convierte en un número de puerta; la cuadra no se deduce aritméticamente a partir de este número.",
        ],
      },
    ],
  },
  {
    id: "door",
    title: "2. Procedimiento de puerta",
    category: "procedures",
    summary: "Contraste de vía, número, territorio y punto de referencia.",
    source: "docs/quality-workflow.md",
    sections: [
      {
        title: "Evidencia necesaria",
        paragraphs: [
          "La aceptación automática requiere una coincidencia exacta o alias explícito y comprobaciones de número de puerta, territorio, punto, CRS y procedencia. Una coordenada de origen no basta para acreditar una puerta.",
        ],
      },
      {
        title: "Cuando no hay aceptación",
        paragraphs: [
          "Un nombre parecido con suficientes comprobaciones puede producir una revisión rápida. La ambigüedad o contradicción requiere una revisión detallada. Estos estados son independientes del flag de entrada.",
          "Los candidatos en revisión se conservan; no avanzan automáticamente hacia una etapa menos precisa.",
        ],
      },
    ],
  },
  {
    id: "block",
    title: "3. Procedimiento de cuadra",
    category: "procedures",
    summary: "Ubicación sobre un tramo real con cuadra declarada.",
    source: "docs/quality-workflow.md",
    sections: [
      {
        title: "Contraste",
        paragraphs: [
          "Se busca la cuadra explícita de la vía dentro del contexto territorial disponible. La referencia debe aportar su geometría real; una tabla de nombres sin línea no basta para producir el tramo.",
        ],
      },
      {
        title: "Precisión del resultado",
        paragraphs: [
          "Una cuadra aceptada conserva la precisión de tramo. No se presenta como una puerta exacta, aunque el formato de la entrada corresponda al flag 1.",
        ],
      },
    ],
  },
  {
    id: "intersection",
    title: "4. Cruce de vías",
    category: "procedures",
    summary: "Dos vías distintas y una intersección documentada.",
    source: "docs/quality-workflow.md",
    sections: [
      {
        title: "Referencia necesaria",
        paragraphs: [
          "La ubicación debe identificar las vías del cruce y su contexto distrital. El motor contrasta la intersección disponible en la referencia y mantiene los controles territoriales y de procedencia.",
        ],
      },
      {
        title: "Continuación",
        paragraphs: [
          "Después del cruce, el motor también dispone de una etapa de vías. El botón Continuar con muestra la siguiente etapa real; no se deben saltar controles para conseguir una aceptación.",
        ],
      },
    ],
  },
  {
    id: "nucleus",
    title: "5. Núcleos urbanos",
    category: "procedures",
    summary: "Núcleos y centros poblados con su precisión propia.",
    source: "docs/quality-workflow.md",
    sections: [
      {
        title: "Qué puede resolver",
        paragraphs: [
          "Contrasta nombres o códigos de núcleos y centros poblados con contexto territorial y referencias documentadas. Los nombres repetidos necesitan elementos suficientes para distinguirlos.",
        ],
      },
      {
        title: "Cómo interpretarlo",
        paragraphs: [
          "El punto de un centro poblado representa esa localidad, no una vivienda. La geometría y la precisión se conservan al visualizar o exportar.",
        ],
      },
    ],
  },
  {
    id: "jurisdiction",
    title: "6. Jurisdicción",
    category: "procedures",
    summary: "Contraste de jurisdicción policial explícita y geometría.",
    source: "docs/quality-workflow.md",
    sections: [
      {
        title: "Contexto requerido",
        paragraphs: [
          "La jurisdicción se identifica mediante evidencia geográfica o una referencia explícita. Pertenecer al mismo distrito no permite escoger por sí solo una jurisdicción policial.",
        ],
      },
      {
        title: "Límites",
        paragraphs: [
          "Una geometría ausente, una procedencia incompleta o un CRS sin confirmar se conservan como limitaciones. Un polígono de jurisdicción no equivale a una puerta exacta.",
        ],
      },
    ],
  },
  {
    id: "coordinates",
    title: "7. Coordenadas",
    category: "procedures",
    summary:
      "Sistema de referencia, orden de ejes y comprobaciones territoriales.",
    source: "docs/quality-workflow.md · docs/review-workflow.md",
    sections: [
      {
        title: "Confirmar antes de utilizar",
        paragraphs: [
          "Los nombres X/Y o latitud/longitud no acreditan el datum. Selecciona WGS84 · EPSG:4326 solo si el proveedor lo documenta y registra el documento que lo confirma. El diccionario de campos y el CRS son evidencias distintas.",
        ],
      },
      {
        title: "Ejecución actual",
        paragraphs: [
          "En el flujo por calidad las coordenadas intervienen en las comprobaciones de coherencia y territorio. No existe una etapa independiente de coordenadas que omita los requisitos de puerta, cuadra u otra referencia.",
          "Una coordenada fuera del territorio, en un límite o contradictoria no se acepta por el simple hecho de estar presente. Los históricos pueden conservar métodos de flujos anteriores.",
        ],
      },
    ],
  },
  {
    id: "sites",
    title: "8. Sitios de interés",
    category: "procedures",
    summary: "Cobertura disponible y referencias adicionales necesarias.",
    source: "docs/quality-workflow.md · docs/limitations.md",
    sections: [
      {
        title: "Cobertura actual",
        paragraphs: [
          "La etapa de núcleos admite puntos de centros poblados documentados. Una búsqueda general de hospitales, colegios, comisarías u otros establecimientos no está disponible como procedimiento independiente en el flujo por calidad.",
        ],
      },
      {
        title: "Qué haría falta",
        paragraphs: [
          "Para ampliar esa cobertura se necesitan referencias con identificadores, nombres, ubicación real, procedencia, versión, CRS y reglas de contraste comprobables. El nombre de un establecimiento no autoriza a inventar su coordenada.",
        ],
      },
    ],
  },
  {
    id: "import",
    title: "Carga y validación de archivos",
    category: "usage",
    summary: "Archivo SIDPOL/PNP y cinco tipos de referencias Excel.",
    source: "docs/quality-workflow.md",
    sections: [
      {
        title: "Antes de procesar",
        steps: [
          "Adjunta el Excel de origen en Vista general.",
          "A su lado, selecciona catálogos guardados o importa Excel de puertas, vías y cuadras, centros poblados, límites administrativos y jurisdicciones.",
          "En cada referencia nueva, lee las columnas, verifica el mapeo y registra institución y versión. Guardar la importación crea un catálogo reutilizable.",
          "En Validación, revisa la hoja, la correspondencia de columnas y los controles de coordenadas. Inicia el procesamiento cuando la configuración sea correcta.",
        ],
      },
      {
        title: "Archivos pendientes",
        paragraphs: [
          "Si interrumpes una carga, vuelve a elegir el mismo archivo para reanudarla. Una referencia guardada con filas pendientes no está completamente habilitada: consulta sus motivos y carga una versión corregida cuando dispongas de geometría o metadatos.",
          "Una línea o polígono no se reconstruye a partir de un nombre. El importador puede conservar esas filas pendientes sin usarlas como evidencia de aceptación.",
        ],
      },
    ],
  },
  {
    id: "review",
    title: "Revisión por excepción",
    category: "review",
    summary: "Resolver candidatos y desbloquear carencias sin repetir trabajo.",
    source: "docs/review-workflow.md",
    sections: [
      {
        title: "Priorizar la acción adecuada",
        paragraphs: [
          "La bandeja distingue casos listos para revisar, casos que necesitan referencia, casos que necesitan datos y problemas técnicos. Importar una capa faltante puede resolver una carencia común; no hace falta revisar esa misma ausencia registro por registro.",
        ],
      },
      {
        title: "Registrar una decisión",
        steps: [
          "Abre una ficha y contrasta origen, candidatos, precisión, motivos e historial.",
          "Toma la reserva de revisión. Una reserva vigente pertenece a su revisor.",
          "Selecciona una decisión y documenta el motivo. Un punto manual exige evidencia.",
          "Guarda y continúa con el siguiente caso del filtro; si sales sin decidir, libera la reserva.",
        ],
      },
      {
        title: "Conservar el progreso",
        paragraphs: [
          "Aceptar manualmente cambia el estado de revisión y conserva el flag de entrada. Si ningún candidato corresponde, registra la decisión adecuada; corregir solo el texto no crea una ubicación geográfica resuelta.",
        ],
      },
    ],
  },
  {
    id: "flags",
    title: "Flags y estados de revisión",
    category: "general",
    summary:
      "Formato de entrada, exclusiones y resolución geográfica por separado.",
    source: "docs/quality-workflow.md · validación de entrada de GeoPol",
    sections: [
      {
        title: "Flags de entrada",
        paragraphs: [
          "Flag 1: dirección de puerta, cuadra, cruce o coordenadas con los componentes requeridos. Flag 2: núcleo y distrito, o vía y jurisdicción explícita. Estas alternativas describen el formato de la ubicación; no acreditan su corrección geográfica. Los flags de origen se conservan por separado.",
          "El flag 10 excluye del procesamiento geográfico y conserva íntegro el registro en resultados y exportaciones. Se respeta cuando viene declarado en origen. Solo se infiere automáticamente cuando todas las celdas de ubicación están literalmente vacías, incluidas coordenadas, UBIGEO, vía y referencias. La falta de mapa, los datos inválidos o una búsqueda sin coincidencias no son motivos para inferirlo.",
        ],
      },
      {
        title: "Estado y precisión",
        paragraphs: [
          "Automático, revisión rápida, revisión detallada, aceptado manualmente y referencia pendiente explican cómo se encuentra la resolución. Un flag 1 con revisión rápida es una combinación válida.",
          "La precisión indica si el resultado corresponde a puerta, cruce, tramo, núcleo u otra referencia. El avance conserva lo resuelto por su estado geográfico, no porque su flag tenga un número menor.",
        ],
      },
    ],
  },
  {
    id: "exports",
    title: "Exportar resultados a Excel",
    category: "formats",
    summary:
      "Descargas filtradas o acumuladas con originales e historial de revisión.",
    source: "docs/excel-exports.md · docs/quality-workflow.md",
    sections: [
      {
        title: "Preparar la descarga",
        steps: [
          "Abre un procesamiento y entra en Exportaciones, o utiliza los filtros de Estadística.",
          "Selecciona el perfil de datos, el filtro que necesites y Excel (.xlsx).",
          "Pulsa Preparar exportación y descarga el archivo cuando termine.",
        ],
      },
      {
        title: "Elegir el perfil",
        paragraphs: [
          "Ubicaciones contiene una fila por unidad de ubicación. El perfil de filas originales conserva los registros de origen vinculados y requiere rol operador o administrador.",
          "El Excel separa flag, estado de revisión, resolución y precisión. Conserva identificadores como texto, coordenadas ausentes vacías y geometrías reales sin centroides inventados. CSV sigue disponible para herramientas GIS.",
        ],
      },
      {
        title: "Instantánea",
        paragraphs: [
          "Una descarga refleja las revisiones vigentes al solicitarla. Si después avanza una etapa o se confirma una revisión, prepara una nueva exportación. No es necesario reimportar el archivo exportado para continuar el procesamiento.",
        ],
      },
    ],
  },
];
const searchable = (value: string) =>
  value
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .toLowerCase();

export function Documentation() {
  const [params, setParams] = useSearchParams();
  const category = categories.some((item) => item.id === params.get("category"))
    ? params.get("category")!
    : "all";
  const query = params.get("q") ?? "";
  const selectedId = params.get("doc");
  const filtered = guides.filter(
    (guide) =>
      (category === "all" || guide.category === category) &&
      searchable(
        `${guide.title} ${guide.summary} ${guide.sections.map((section) => `${section.title} ${section.paragraphs?.join(" ") ?? ""} ${section.steps?.join(" ") ?? ""}`).join(" ")}`,
      ).includes(searchable(query.trim())),
  );
  const selected =
    filtered.find((guide) => guide.id === selectedId) ?? filtered[0];
  const reader = useRef<HTMLElement>(null);
  const searchInput = useRef<HTMLInputElement>(null);
  const [catalogOpen, setCatalogOpen] = useState(() => !!query);
  const selectedCategory = categories.find(
    (item) => item.id === selected?.category,
  );
  function filter(key: "category" | "q", value: string) {
    const next = new URLSearchParams(params);
    if (value && value !== "all") next.set(key, value);
    else next.delete(key);
    next.delete("doc");
    setCatalogOpen(true);
    setParams(next, { replace: key === "q" });
  }
  function choose(id: string) {
    const next = new URLSearchParams(params);
    next.set("doc", id);
    setCatalogOpen(false);
    setParams(next);
    if (window.matchMedia?.("(max-width: 1000px)").matches) {
      requestAnimationFrame(() => {
        reader.current?.focus();
        reader.current?.scrollIntoView({ block: "start" });
      });
    }
  }
  return (
    <>
      <PageHeader
        title="Documentación"
        description="Consulta cómo cargar archivos, resolver ubicaciones y revisar resultados."
      />
      <div className="documentation-workspace">
        <div className="documentation-tools">
          <label className="documentation-search">
            <span className="sr-only">Buscar documentos</span>
            <Search size={20} aria-hidden="true" />
            <input
              ref={searchInput}
              inputMode="search"
              value={query}
              placeholder="Buscar por tema o procedimiento…"
              onChange={(event) => filter("q", event.target.value)}
            />
          </label>
          {query && (
            <button
              className="documentation-clear"
              type="button"
              aria-label="Limpiar búsqueda"
              onClick={() => {
                filter("q", "");
                searchInput.current?.focus();
              }}
            >
              <X size={18} aria-hidden="true" />
            </button>
          )}
        </div>
        <nav
          className="documentation-categories"
          aria-label="Categorías de documentación"
        >
          {categories.map((item) => (
            <button
              key={item.id}
              type="button"
              className={`documentation-tone-${item.tone}`}
              aria-pressed={category === item.id}
              onClick={() => filter("category", item.id)}
            >
              <item.icon size={18} aria-hidden="true" />
              <span>{item.label}</span>
            </button>
          ))}
        </nav>
        <div
          className={`documentation-reading-layout${selected ? "" : " is-empty"}`}
        >
          <section
            className="documentation-catalog"
            aria-labelledby="documentation-list-title"
            data-open={catalogOpen}
          >
            <div className="documentation-catalog-heading">
              <h2 id="documentation-list-title">Guías disponibles</h2>
              <span role="status" aria-label="Cantidad de guías disponibles">
                {filtered.length}
              </span>
            </div>
            {filtered.length > 0 && (
              <button
                className="documentation-catalog-toggle"
                type="button"
                aria-expanded={catalogOpen}
                aria-controls="documentation-catalog-content"
                onClick={() => setCatalogOpen(!catalogOpen)}
              >
                <Library size={20} aria-hidden="true" />
                <span>
                  {catalogOpen ? "Ocultar catálogo" : "Explorar guías"}
                  <small>{filtered.length} disponibles</small>
                </span>
                <ChevronDown size={18} aria-hidden="true" />
              </button>
            )}
            <div
              id="documentation-catalog-content"
              className="documentation-catalog-content"
            >
              <div className="documentation-list">
                {filtered.map((guide) => {
                  const group = categories.find(
                    (item) => item.id === guide.category,
                  )!;
                  return (
                    <button
                      key={guide.id}
                      type="button"
                      className={`documentation-card documentation-tone-${group.tone}`}
                      aria-pressed={selected?.id === guide.id}
                      onClick={() => choose(guide.id)}
                    >
                      <span className="documentation-guide-icon">
                        <group.icon size={19} aria-hidden="true" />
                      </span>
                      <span className="documentation-guide-copy">
                        <strong>{guide.title}</strong>
                        {category === "all" && <small>{group.label}</small>}
                      </span>
                      <ChevronRight size={17} aria-hidden="true" />
                    </button>
                  );
                })}
              </div>
              {!filtered.length && (
                <Empty
                  title="No se encontraron documentos"
                  text="Prueba otro término o consulta todas las categorías."
                  action={
                    <button
                      className="button secondary"
                      onClick={() => {
                        setParams({});
                        setCatalogOpen(true);
                      }}
                    >
                      Mostrar todos
                    </button>
                  }
                />
              )}
            </div>
          </section>
          {selected && (
            <article
              ref={reader}
              id="documentation-reader"
              className={`panel documentation-reader documentation-tone-${selectedCategory?.tone ?? "cyan"}`}
              tabIndex={-1}
              aria-labelledby="documentation-reader-title"
            >
              <header className="documentation-reader-heading">
                <span>
                  {selectedCategory && (
                    <selectedCategory.icon size={19} aria-hidden="true" />
                  )}
                  {selectedCategory?.label}
                </span>
                <h2 id="documentation-reader-title">{selected.title}</h2>
                <p className="documentation-lead">{selected.summary}</p>
              </header>
              <div className="documentation-reader-body">
                {selected.sections.map((section) => (
                  <section key={section.title}>
                    <h3>{section.title}</h3>
                    {section.paragraphs?.map((paragraph) => (
                      <p key={paragraph}>{paragraph}</p>
                    ))}
                    {section.steps && (
                      <ol>
                        {section.steps.map((step) => (
                          <li key={step}>{step}</li>
                        ))}
                      </ol>
                    )}
                  </section>
                ))}
              </div>
            </article>
          )}
        </div>
      </div>
    </>
  );
}
