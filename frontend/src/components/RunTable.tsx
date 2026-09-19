import { FileSpreadsheet } from "lucide-react";
import { date, number } from "../lib/format";
import type { Run } from "../types";
import { Badge, Empty, ViewLink } from "./ui";
export function RunTable({ runs }: { runs: Run[] }) {
  if (!runs.length)
    return (
      <Empty
        title="Tu primer procesamiento empieza aquí"
        text="Carga un CSV o XLSX para normalizar direcciones y evaluar su ubicación con fuentes trazables."
        action={<ViewLink to="/runs/new">Crear procesamiento</ViewLink>}
      />
    );
  return (
    <div className="table-scroll">
      <table>
        <thead>
          <tr>
            <th>Procesamiento</th>
            <th>Estado</th>
            <th>Filas de origen</th>
            <th>Ubicaciones</th>
            <th>Creado</th>
            <th>
              <span className="sr-only">Acciones</span>
            </th>
          </tr>
        </thead>
        <tbody>
          {runs.map((run) => (
            <tr key={run.id}>
              <td>
                <div className="file-cell">
                  <span className="file-icon">
                    <FileSpreadsheet size={19} aria-hidden="true" />
                  </span>
                  <div>
                    <strong>{run.name}</strong>
                    <small>{run.filename}</small>
                  </div>
                </div>
              </td>
              <td>
                <Badge value={run.status} />
              </td>
              <td className="numeric">{number(run.source_rows)}</td>
              <td className="numeric">{number(run.location_units)}</td>
              <td className="muted nowrap">{date(run.created_at)}</td>
              <td>
                <ViewLink to={`/runs/${run.id}`} />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
