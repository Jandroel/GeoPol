import { useId, useState, type CSSProperties } from "react";
import { number } from "../lib/format";
import { percentage } from "../lib/quality";
import type { QualityOverview } from "../types";
import "./quality-visuals.css";

const categories = [
  {
    key: "resolved",
    label: "Resueltos",
    shortLabel: "resueltos",
    color: "var(--success)",
  },
  {
    key: "review",
    label: "Por revisar",
    shortLabel: "por revisar",
    color: "var(--amber)",
  },
  {
    key: "unmatched",
    label: "Sin coincidencia",
    shortLabel: "sin coincidencia",
    color: "var(--accent)",
  },
  {
    key: "blocked",
    label: "Referencia o datos pendientes",
    shortLabel: "referencia pendiente",
    color: "var(--slate)",
  },
] as const;
type Category = (typeof categories)[number]["key"];

/** Historical stage distribution. Exploring a segment never filters current results. */
export function StageChart({
  stage,
}: {
  stage: QualityOverview["stages"][number];
}) {
  const descriptionId = useId();
  const [selected, setSelected] = useState<Category | null>(null);
  const [hovered, setHovered] = useState<Category | null>(null);
  const [focused, setFocused] = useState<Category | null>(null);
  const active = hovered ?? focused ?? selected;
  const category = categories.find((item) => item.key === active);
  let offset = 0;
  const segments = categories.map((item) => {
    const share = stage.units ? (stage[item.key] / stage.units) * 100 : 0;
    const start = offset;
    offset += share;
    return { ...item, share, start };
  });
  function clearSelection() {
    setSelected(null);
    setHovered(null);
    setFocused(null);
  }
  return (
    <div
      className="stage-visual"
      onKeyDown={(event) => {
        if (event.key === "Escape") clearSelection();
      }}
    >
      <div className="stage-visual-layout">
        <div className="stage-ring">
          <svg
            viewBox="0 0 180 180"
            aria-hidden="true"
            className="stage-ring-svg"
          >
            <circle className="stage-ring-track" cx="90" cy="90" r="68" />
            {segments
              .filter((item) => item.share > 0)
              .map((item) => (
                <circle
                  key={item.key}
                  className={`stage-ring-segment${active === item.key ? " is-highlighted" : ""}${active && active !== item.key ? " is-muted" : ""}`}
                  cx="90"
                  cy="90"
                  r="68"
                  pathLength="100"
                  strokeDasharray={`${Math.max(0, item.share - (item.share === 100 ? 0 : Math.min(0.65, item.share / 5)))} 100`}
                  transform={`rotate(${item.start * 3.6 - 90} 90 90)`}
                  style={{ "--chart-color": item.color } as CSSProperties}
                  onMouseEnter={() => setHovered(item.key)}
                  onMouseLeave={() => setHovered(null)}
                  onClick={() =>
                    setSelected(selected === item.key ? null : item.key)
                  }
                  data-category={item.key}
                />
              ))}
          </svg>
          <div className="stage-ring-value" aria-hidden="true">
            <strong>{number(active ? stage[active] : stage.units)}</strong>
            {active && (
              <span className="stage-ring-percentage">
                {percentage(stage[active], stage.units)}
              </span>
            )}
            <span>{category ? category.shortLabel : "evaluadas"}</span>
            {!active && <small>en esta etapa</small>}
          </div>
        </div>
        <table className="quality-legend stage-chart-table">
          <caption className="sr-only">
            Distribución de {stage.label}. Porcentajes sobre {stage.units}{" "}
            ubicaciones evaluadas en esta etapa.
          </caption>
          <thead className="sr-only">
            <tr>
              <th>Estado</th>
              <th>Cantidad</th>
              <th>Porcentaje</th>
            </tr>
          </thead>
          <tbody>
            {categories.map((item) => (
              <tr
                key={item.key}
                className={active === item.key ? "is-highlighted" : ""}
                style={{ "--chart-color": item.color } as CSSProperties}
              >
                <th scope="row">
                  <button
                    type="button"
                    className="stage-legend-button"
                    aria-pressed={selected === item.key}
                    aria-describedby={descriptionId}
                    onMouseEnter={() => setHovered(item.key)}
                    onMouseLeave={() => setHovered(null)}
                    onFocus={() => setFocused(item.key)}
                    onBlur={() => setFocused(null)}
                    onClick={() =>
                      setSelected(selected === item.key ? null : item.key)
                    }
                  >
                    <span className="stage-legend-swatch" aria-hidden="true" />
                    <span>{item.label}</span>
                    <span className="sr-only">
                      : {number(stage[item.key])} de {number(stage.units)},{" "}
                      {percentage(stage[item.key], stage.units)}
                    </span>
                  </button>
                </th>
                <td>{number(stage[item.key])}</td>
                <td>{percentage(stage[item.key], stage.units)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="stage-visual-detail">
        <p id={descriptionId} aria-live="polite" aria-atomic="true">
          {stage.units === 0
            ? "Esta etapa aún no tiene ubicaciones evaluadas."
            : category && active
              ? `${category.label}: ${number(stage[active])} de ${number(stage.units)} evaluadas en esta etapa (${percentage(stage[active], stage.units)}).`
              : `Base del gráfico: ${number(stage.units)} ubicaciones evaluadas en esta etapa.`}
        </p>
        <button
          type="button"
          className="stage-total-button"
          onClick={clearSelection}
          disabled={!active}
        >
          Ver total
        </button>
      </div>
    </div>
  );
}
