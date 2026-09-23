import { useId, useState, type CSSProperties } from "react";
import { number } from "../lib/format";
import { percentage } from "../lib/quality";
import type { QualityOverview } from "../types";
import "./quality-visuals.css";

const categories = [
  {
    key: "resolved",
    label: "Resueltos",
    color: "var(--success)",
    textColor: "var(--surface)",
  },
  {
    key: "review",
    label: "Por revisar",
    color: "var(--amber)",
    textColor: "var(--surface)",
  },
  {
    key: "unmatched",
    label: "Sin coincidencia",
    color: "var(--accent)",
    textColor: "var(--chart-ink)",
  },
  {
    key: "blocked",
    label: "Referencia o datos pendientes",
    color: "var(--slate)",
    textColor: "var(--chart-ink)",
  },
] as const;
type Category = (typeof categories)[number]["key"];

const center = 120;
const radius = 94;
function point(turn: number, distance = radius) {
  const angle = turn * 2 * Math.PI - Math.PI / 2;
  return [
    center + Math.cos(angle) * distance,
    center + Math.sin(angle) * distance,
  ];
}
function slice(start: number, share: number) {
  const [x1, y1] = point(start);
  const [x2, y2] = point(start + share);
  return `M ${center} ${center} L ${x1} ${y1} A ${radius} ${radius} 0 ${share > 0.5 ? 1 : 0} 1 ${x2} ${y2} Z`;
}

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
    const share = stage.units ? stage[item.key] / stage.units : 0;
    const start = offset;
    offset += share;
    const [x, y] = point(start + share / 2, 7);
    const label =
      share === 1 ? [center, center] : point(start + share / 2, radius * 0.61);
    return {
      ...item,
      share,
      start,
      label,
      dx: share === 1 ? 0 : x - center,
      dy: share === 1 ? 0 : y - center,
    };
  });
  const activeSegment = segments.find((item) => item.key === active);
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
        <div className="stage-pie-figure">
          <div className="stage-pie-canvas">
            <svg viewBox="0 0 240 240" aria-hidden="true" className="stage-pie">
              {stage.units === 0 && (
                <>
                  <circle
                    className="stage-pie-empty"
                    cx={center}
                    cy={center}
                    r={radius}
                  />
                  <text
                    className="stage-pie-empty-label"
                    x={center}
                    y={center}
                    textAnchor="middle"
                    dominantBaseline="middle"
                  >
                    Sin datos
                  </text>
                </>
              )}
              {segments
                .filter((item) => item.share > 0)
                .map((item) => {
                  const highlighted = active === item.key;
                  const Shape = item.share === 1 ? "circle" : "path";
                  const geometry =
                    item.share === 1
                      ? { cx: center, cy: center, r: radius }
                      : { d: slice(item.start, item.share) };
                  return (
                    <g
                      key={item.key}
                      data-slice={item.key}
                      className={`stage-pie-slice${highlighted ? " is-highlighted" : ""}${active && !highlighted ? " is-muted" : ""}`}
                      style={
                        {
                          "--chart-color": item.color,
                          "--slice-text": item.textColor,
                          "--slice-x": `${item.dx}px`,
                          "--slice-y": `${item.dy}px`,
                        } as CSSProperties
                      }
                      onMouseEnter={() => setHovered(item.key)}
                      onMouseLeave={() => setHovered(null)}
                      onClick={() =>
                        setSelected(selected === item.key ? null : item.key)
                      }
                    >
                      {/* Keep the hit area stationary while its visible slice moves. */}
                      <Shape {...geometry} className="stage-pie-hit" />
                      <g className="stage-pie-piece">
                        {highlighted && (
                          <Shape {...geometry} className="stage-pie-halo" />
                        )}
                        <Shape
                          {...geometry}
                          className={`stage-pie-segment${highlighted ? " is-highlighted" : ""}`}
                          data-category={item.key}
                          style={{ strokeWidth: item.share < 0.02 ? 0 : 1.5 }}
                        />
                        {item.share >= 0.12 && (
                          <text
                            className="stage-pie-label"
                            x={item.label[0]}
                            y={item.label[1]}
                            textAnchor="middle"
                            dominantBaseline="middle"
                          >
                            {percentage(stage[item.key], stage.units)}
                          </text>
                        )}
                      </g>
                    </g>
                  );
                })}
            </svg>
            {category && active && (
              <div
                className="stage-pie-tooltip"
                data-side={
                  activeSegment && activeSegment.label[1] >= center
                    ? "top"
                    : "bottom"
                }
                aria-hidden="true"
              >
                <span>
                  <i style={{ background: category.color }} />
                  {category.label}
                </span>
                <strong>
                  {number(stage[active])}
                  <span>{percentage(stage[active], stage.units)}</span>
                </strong>
              </div>
            )}
          </div>
          <div className="stage-pie-total">
            <strong>{number(stage.units)}</strong> ubicaciones evaluadas
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
