import { CheckCircle2, CircleAlert, LoaderCircle } from "lucide-react";
import { number } from "../lib/format";
import { ErrorNotice } from "./ui";

export interface InputValidationReport {
  filename: {
    valid: boolean;
    expected: string;
    date: string | null;
    message: string;
  };
  columns: {
    detected: string[];
    required: string[];
    missing: string[];
    mapping: Record<string, string>;
  };
  flag_column_present: boolean;
  total_rows: number;
  flag10_existing: number;
  flag10_autoeligible: number;
  issue_rows: number;
  warnings: string[];
  ready: boolean;
}

export function InputValidationPanel({
  report,
  pending,
  error,
}: {
  report?: InputValidationReport;
  pending: boolean;
  error: unknown;
}) {
  return (
    <section
      className="panel input-validation-panel"
      aria-label="Comprobaciones del archivo"
      aria-busy={pending}
    >
      <div className="panel-heading">
        <div>
          <h2>Comprobaciones del archivo</h2>
          <p>
            La validación revisa la estructura. La ubicación se contrasta
            durante los procedimientos.
          </p>
        </div>
        {pending && (
          <span className="validation-pending" role="status">
            <LoaderCircle size={18} aria-hidden="true" /> Revisando…
          </span>
        )}
      </div>
      <ErrorNotice error={error} />
      {report && (
        <>
          <div className="validation-checks">
            {[
              {
                title: "Nombre y fecha",
                ok: report.filename.valid,
                text: report.filename.message,
              },
              {
                title: "Columnas de ubicación",
                ok: report.columns.missing.length === 0,
                text: report.columns.missing.length
                  ? `Faltan: ${report.columns.missing.join(", ")}`
                  : `${number(report.columns.detected.length)} columnas identificadas; revisa el mapeo.`,
              },
              {
                title: "Columna FLAG",
                ok: report.flag_column_present,
                text: report.flag_column_present
                  ? "Se conservarán los valores de origen."
                  : "Se calculará el flag durante el procesamiento y se incluirá en la exportación.",
              },
            ].map((check) => (
              <div
                className={`validation-check ${check.ok ? "is-valid" : "has-notice"}`}
                key={check.title}
              >
                {check.ok ? (
                  <CheckCircle2 size={20} aria-label="Comprobado" />
                ) : (
                  <CircleAlert size={20} aria-label="Observación" />
                )}
                <div>
                  <strong>{check.title}</strong>
                  <p>{check.text}</p>
                </div>
              </div>
            ))}
          </div>
          <dl className="validation-counts">
            <div>
              <dt>Filas del archivo</dt>
              <dd>{number(report.total_rows)}</dd>
            </div>
            <div>
              <dt>FLAG 10 de origen</dt>
              <dd>{number(report.flag10_existing)}</dd>
            </div>
            <div>
              <dt>Sin datos para ubicar</dt>
              <dd>{number(report.flag10_autoeligible)}</dd>
            </div>
          </dl>
          <p className="field-hint">
            El FLAG 10 conserva la fila y la separa del procesamiento
            geográfico. Una dirección sin coincidencia sigue disponible para
            revisión.
          </p>
          {!!report.warnings.length && (
            <details>
              <summary>
                Observaciones del archivo ({report.warnings.length})
              </summary>
              <ul>
                {report.warnings.map((warning, i) => (
                  <li key={i}>{warning}</li>
                ))}
              </ul>
            </details>
          )}
          {!report.ready && (
            <p role="status" className="validation-blocked">
              Revisa las columnas y los datos del archivo antes de iniciar.
            </p>
          )}
        </>
      )}
    </section>
  );
}
