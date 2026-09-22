import { Notice } from "./ui";

export const documentedCrs = (config: Record<string, unknown>) =>
  config.crs === "EPSG:4326" &&
  typeof config.crs_evidence === "string" &&
  config.crs_evidence.trim().length >= 8 &&
  config.crs_evidence.trim().length <= 500;

export function CoordinatePolicy({
  confirmed,
  evidence,
  onConfirmed,
  onEvidence,
  disabled = false,
}: {
  confirmed: boolean;
  evidence: string;
  onConfirmed: (value: boolean) => void;
  onEvidence: (value: string) => void;
  disabled?: boolean;
}) {
  return (
    <section
      className="stack"
      aria-label="Confirmación del sistema de coordenadas"
    >
      <label>
        Sistema de coordenadas originales
        <select
          aria-label="Sistema de coordenadas originales"
          value={confirmed ? "EPSG:4326" : "unconfirmed"}
          onChange={(e) => onConfirmed(e.target.value === "EPSG:4326")}
          disabled={disabled}
        >
          <option value="unconfirmed">
            Sin confirmar el sistema de coordenadas
          </option>
          <option value="EPSG:4326">WGS84 · EPSG:4326 documentado</option>
        </select>
      </label>
      {confirmed ? (
        <label>
          Fuente de confirmación de WGS84
          <textarea
            aria-label="Fuente de confirmación de WGS84"
            required
            minLength={8}
            maxLength={500}
            value={evidence}
            onChange={(e) => onEvidence(e.target.value)}
            disabled={disabled}
            placeholder="Documento, metadatos o responsable que confirma el sistema de coordenadas del archivo."
          />
          <span className="field-hint">
            No basta que los valores parezcan latitud y longitud. Esta opción no
            transforma coordenadas UTM ni otros sistemas.
          </span>
        </label>
      ) : (
        <Notice>
          Puedes procesar las direcciones con las referencias disponibles. Las
          coordenadas originales se conservarán como declaradas, sin aceptarlas
          automáticamente mientras su sistema no esté documentado.
        </Notice>
      )}
    </section>
  );
}
