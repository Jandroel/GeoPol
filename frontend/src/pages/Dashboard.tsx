import { useQuery } from "@tanstack/react-query";
import {
  CheckCheck,
  ClipboardCheck,
  Files,
  Layers3,
  MapPin,
  Plus,
} from "lucide-react";
import { Link } from "react-router-dom";
import { request } from "../lib/api";
import { number } from "../lib/format";
import type { Dashboard as DashboardData } from "../types";
import { ErrorNotice, Loading, PageHeader, ViewLink } from "../components/ui";
import { RunTable } from "../components/RunTable";
import { useAuth } from "../auth";
export function Dashboard() {
  const { user } = useAuth();
  const data = useQuery({
    queryKey: ["dashboard"],
    queryFn: () => request<DashboardData>("/dashboard"),
    refetchInterval: 15000,
  });
  if (data.isPending) return <Loading />;
  if (data.isError) return <ErrorNotice error={data.error} />;
  const d = data.data;
  const allowed = ["admin", "operator"].includes(user?.role ?? "");
  const other = Math.max(
    0,
    d.location_units - d.accepted - d.review_required - d.unresolved,
  );
  const segments = [
    { name: "Aceptadas", value: d.accepted, color: "var(--success)" },
    { name: "En evaluación", value: d.review_required, color: "var(--amber)" },
    { name: "Sin resolver", value: d.unresolved, color: "var(--slate)" },
    { name: "Otros estados", value: other, color: "var(--border)" },
  ];
  return (
    <>
      <PageHeader
        title="Resumen"
        actions={
          allowed && (
            <Link className="button primary" to="/runs/new">
              <Plus size={18} aria-hidden="true" />
              Nuevo procesamiento
            </Link>
          )
        }
      />
      <div className="scope-label">
        <span className="tiny-dot" />
        Los indicadores de ubicación corresponden a las ejecuciones terminadas
        vigentes. Procesamientos incluye todo el historial.
      </div>
      <div className="stats-grid">
        {[
          {
            title: "Procesamientos",
            value: d.runs,
            subtitle: undefined,
            icon: Files,
          },
          {
            title: "Filas de origen",
            value: d.source_rows,
            subtitle: undefined,
            icon: Layers3,
          },
          {
            title: "Unidades de ubicación",
            value: d.location_units,
            subtitle: "Agrupadas por denuncia y lugar",
            icon: MapPin,
          },
          {
            title: "Pendientes de atención",
            value: d.review_open,
            subtitle: `${number(d.review_actionable)} con evidencia para decidir`,
            icon: ClipboardCheck,
          },
        ].map((s, i) => (
          <article
            className={`stat-card ${i === 3 ? "highlight" : ""}`}
            key={s.title}
          >
            <div className="stat-top">
              <span>{s.title}</span>
              <s.icon size={20} aria-hidden="true" />
            </div>
            <strong>{number(s.value)}</strong>
            {s.subtitle && <small>{s.subtitle}</small>}
            {i === 3 && <ViewLink to="/review">Abrir bandeja</ViewLink>}
          </article>
        ))}
      </div>
      <section className="panel distribution dashboard-distribution">
        <div className="panel-heading">
          <div>
            <h2>Resolución de ubicaciones</h2>
          </div>
          <CheckCheck size={22} className="muted" aria-hidden="true" />
        </div>
        <div className="distribution-body">
          <div
            className="donut"
            style={{
              background: d.location_units
                ? `conic-gradient(var(--success) 0 ${(d.accepted / d.location_units) * 100}%,var(--amber) ${(d.accepted / d.location_units) * 100}% ${((d.accepted + d.review_required) / d.location_units) * 100}%,var(--slate) ${((d.accepted + d.review_required) / d.location_units) * 100}% ${((d.accepted + d.review_required + d.unresolved) / d.location_units) * 100}%,var(--border) 0)`
                : "var(--border)",
            }}
            role="img"
            aria-label={`${number(d.location_units)} ubicaciones: ${segments.map((s) => `${s.value} ${s.name}`).join(", ")}`}
          >
            <div>
              <strong>
                {d.location_units
                  ? `${Math.round((d.accepted / d.location_units) * 100)}%`
                  : "—"}
              </strong>
              <span>aceptadas</span>
            </div>
          </div>
          <div className="chart-legend">
            {segments
              .filter((s, i) => i < 3 || s.value > 0)
              .map((s) => (
                <div key={s.name}>
                  <span className="legend-label">
                    <i style={{ background: s.color }} />
                    {s.name}
                  </span>
                  <strong>{number(s.value)}</strong>
                </div>
              ))}
          </div>
        </div>
      </section>
      <section className="panel">
        <div className="panel-heading">
          <div>
            <h2>Procesamientos recientes</h2>
          </div>
          <ViewLink to="/runs">Ver todos</ViewLink>
        </div>
        <RunTable runs={d.recent_runs} />
      </section>
    </>
  );
}
