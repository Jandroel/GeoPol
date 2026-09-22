import type { Reference } from "../types";
import { number } from "../lib/format";

const kinds: Record<string, string> = {
  door: "puertas",
  block: "cuadras",
  intersection: "intersecciones",
  street: "vías",
  manzana: "manzanas",
  site: "sitios",
  nucleus: "núcleos",
  jurisdiction: "jurisdicciones",
  boundary: "límites territoriales",
};

export function ReferenceCapability({ catalog }: { catalog: Reference }) {
  return (
    <div className="reference-capability">
      <p>
        <strong>
          {catalog.name} · {catalog.version}
        </strong>
        <br />
        {catalog.source}
      </p>
      <p>
        {number(catalog.feature_count)} elementos
        {catalog.kinds?.length
          ? ` · ${catalog.kinds.map((kind) => kinds[kind] ?? kind).join(", ")}`
          : ""}
        .
      </p>
      <p className="field-hint">
        La automatización depende de que la fuente cubra el distrito y la
        dirección. Un mapa de fondo ayuda a visualizar; el catálogo aporta la
        evidencia para resolver.
      </p>
    </div>
  );
}
