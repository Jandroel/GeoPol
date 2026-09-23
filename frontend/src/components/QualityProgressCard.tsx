import type { CSSProperties, ReactNode } from "react";
import { ArrowRight, Layers3 } from "lucide-react";
import { number } from "../lib/format";
import { percentage, qualityStageLabel } from "../lib/quality";
import type { QualityOverview } from "../types";
import "./quality-visuals.css";

export function QualityProgressCard({
  data,
  active,
  busy,
  canManage,
  superseded,
  onAdvance,
  error,
}: {
  data: QualityOverview;
  active: boolean;
  busy: boolean;
  canManage: boolean;
  superseded: boolean;
  onAdvance: (stage: string) => void;
  error?: ReactNode;
}) {
  const { resolved, units, source_rows } = data.totals;
  const share = units ? Math.min(1, Math.max(0, resolved / units)) : 0;
  return (
    <section
      className="panel quality-progress-summary quality-progress-card"
      aria-labelledby="quality-progress-heading"
    >
      <div className="quality-progress-main">
        <div className="quality-progress-heading">
          <div>
            <h2 id="quality-progress-heading">Avance por calidad</h2>
            <p>Ubicaciones resueltas y conservadas</p>
          </div>
        </div>
        <div className="quality-progress-measure">
          <strong>{percentage(resolved, units)}</strong>
          <p>
            <b>{number(resolved)}</b> de <b>{number(units)}</b> ubicaciones
            resueltas
          </p>
        </div>
        <div
          className="quality-progress-track"
          role="progressbar"
          aria-label="Ubicaciones resueltas"
          aria-valuenow={resolved}
          aria-valuemin={0}
          aria-valuemax={Math.max(1, units)}
          aria-valuetext={`${number(resolved)} de ${number(units)} ubicaciones resueltas (${percentage(resolved, units)})`}
        >
          <span style={{ "--quality-progress": share } as CSSProperties} />
        </div>
        <p className="quality-progress-source">
          El archivo original contiene {number(source_rows)} filas.
        </p>
      </div>
      <div className="quality-progress-next">
        <div className="quality-next-title">
          <Layers3 size={19} aria-hidden="true" />
          <span>
            {active
              ? "Procesamiento activo"
              : data.next_stage
                ? "Próxima etapa"
                : "Balance de la ejecución"}
          </span>
        </div>
        <h3>
          {active
            ? "Evaluando ubicaciones"
            : data.next_stage
              ? qualityStageLabel(data.next_stage)
              : units > 0 && resolved === units
                ? "Todas las ubicaciones resueltas"
                : "Sin otra etapa disponible"}
        </h3>
        {!active && data.next_stage && (
          <p className="quality-eligible">
            <strong>{number(data.eligible_units)}</strong> ubicaciones elegibles
            para continuar
          </p>
        )}
        {error}
        {!active && data.next_stage && canManage && (
          <button
            type="button"
            className="button primary quality-next-button"
            disabled={busy || active || !data.can_advance || superseded}
            onClick={() => onAdvance(data.next_stage!)}
          >
            {busy
              ? "Iniciando etapa…"
              : `Continuar con ${qualityStageLabel(data.next_stage).toLowerCase()}`}
            <ArrowRight size={18} aria-hidden="true" />
          </button>
        )}
        {active && (
          <p className="quality-progress-note" role="status">
            Etapa en procesamiento. Los conteos se actualizan automáticamente.
          </p>
        )}
        <p className="quality-progress-note">
          Los resueltos se conservan al avanzar.{" "}
          {number(data.held_review_units)} ubicaciones esperan revisión y no
          pasan automáticamente a una etapa menos precisa.
        </p>
      </div>
    </section>
  );
}
