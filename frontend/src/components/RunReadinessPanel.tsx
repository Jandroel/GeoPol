import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { request } from "../lib/api";
import { number } from "../lib/format";
import { reviewBuckets, type ReviewBucket } from "../lib/review";
import type { RunReadiness } from "../types";
import { ErrorNotice, Loading, Notice } from "./ui";

export function RunReadinessPanel({
  runId,
  canManage,
}: {
  runId: string;
  canManage: boolean;
}) {
  const query = useQuery({
    queryKey: ["run-readiness", runId],
    queryFn: () => request<RunReadiness>(`/runs/${runId}/readiness`),
  });
  if (query.isPending) return <Loading text="Revisando causas comunes…" />;
  if (query.isError) return <ErrorNotice error={query.error} />;
  const data = query.data;
  return (
    <section
      className="panel form-panel readiness-panel"
      aria-label="Cómo resolver los pendientes"
    >
      <div className="panel-heading">
        <div>
          <h2>Cómo resolver los pendientes</h2>
          <p>
            Actúa sobre las causas comunes antes de abrir fichas individuales.
          </p>
        </div>
        <Link
          className="button secondary"
          to={`/review?run_id=${runId}&bucket=actionable&stage=open`}
        >
          Abrir revisión de esta ejecución
        </Link>
      </div>
      {data.coordinates.legacy_unconfirmed && (
        <Notice>
          Esta ejecución asumió WGS84 sin documentar su origen. Al reprocesar,
          confirma el sistema con una fuente o conserva las coordenadas sin
          aceptación automática.
        </Notice>
      )}
      {data.review.total_open === 0 ? (
        <p>No hay ubicaciones pendientes en esta ejecución.</p>
      ) : (
        <div className="readiness-causes">
          {data.review.causes
            .filter((cause) => cause.count > 0)
            .map((cause) => (
              <article key={cause.bucket}>
                <h3>
                  {number(cause.count)} ·{" "}
                  {reviewBuckets[cause.bucket as ReviewBucket]?.label ??
                    "Pendientes"}
                </h3>
                <p>{cause.action}</p>
                {cause.bucket === "needs_reference" ? (
                  <div className="button-row">
                    <Link className="button secondary" to="/references">
                      Resolver la referencia
                    </Link>
                    {canManage && (
                      <Link
                        className="button primary"
                        to={`/runs/${runId}?tab=reprocess`}
                      >
                        Reprocesar con referencia
                      </Link>
                    )}
                  </div>
                ) : cause.bucket === "actionable" ? (
                  <Link
                    className="text-link"
                    to={`/review?run_id=${runId}&bucket=actionable&stage=open`}
                  >
                    Revisar candidatos y equivalencias
                  </Link>
                ) : (
                  <Link
                    className="text-link"
                    to={`/review?run_id=${runId}&bucket=${cause.bucket}&stage=open`}
                  >
                    {cause.bucket === "needs_data"
                      ? "Consultar los datos que faltan"
                      : "Consultar incidencias"}
                  </Link>
                )}
              </article>
            ))}
        </div>
      )}
      {data.reference.status !== "ready" &&
        data.processing_defaults.status === "ready" && (
          <Notice>
            Ya hay una referencia base disponible:{" "}
            <strong>{data.processing_defaults.catalog?.name}</strong>.
            Reprocesar con ella evaluará de nuevo el lote completo; no modifica
            las decisiones históricas.
          </Notice>
        )}
    </section>
  );
}
