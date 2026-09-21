import { useQuery } from "@tanstack/react-query";
import {
  ArrowRight,
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
    { name: "Aceptadas", value: d.accepted, color: "var(--teal)" },
    { name: "En evaluación", value: d.review_required, color: "var(--amber)" },
    { name: "Sin resolver", value: d.unresolved, color: "var(--slate)" },
    { name: "Otros estados", value: other, color: "var(--border)" },
  ];
  return (
    <>
      <PageHeader
        eyebrow="CONTROL OPERATIVO"
        title="Una mirada a tu territorio"
        description="Supervisa la calidad de las ubicaciones y continúa donde lo dejaste."
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
        Ubicaciones de ejecuciones terminadas vigentes · Historial de
        procesamientos completo
      </div>
      <div className="stats-grid">
        {[
          {
            title: "Procesamientos",
            value: d.runs,
            subtitle: "Historial completo",
            icon: Files,
          },
          {
            title: "Filas de origen",
            value: d.source_rows,
            subtitle: "En ejecuciones vigentes",
            icon: Layers3,
          },
          {
            title: "Unidades de ubicación",
            value: d.location_units,
            subtitle: "Agrupadas por denuncia y lugar",
            icon: MapPin,
          },
          {
            title: "Listas para revisar",
            value: d.review_actionable,
            subtitle: "Pendientes con evidencia para decidir",
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
            <small>{s.subtitle}</small>
          </article>
        ))}
      </div>
      <div className="dashboard-grid">
        <section className="panel distribution">
          <div className="panel-heading">
            <div>
              <h2>Resolución de ubicaciones</h2>
              <p>Clasificación de ubicaciones vigentes</p>
            </div>
            <CheckCheck size={22} className="muted" aria-hidden="true" />
          </div>
          <div className="distribution-body">
            <div
              className="donut"
              style={{
                background: d.location_units
                  ? `conic-gradient(var(--teal) 0 ${(d.accepted / d.location_units) * 100}%,var(--amber) ${(d.accepted / d.location_units) * 100}% ${((d.accepted + d.review_required) / d.location_units) * 100}%,var(--slate) ${((d.accepted + d.review_required) / d.location_units) * 100}% ${((d.accepted + d.review_required + d.unresolved) / d.location_units) * 100}%,var(--border) 0)`
                  : "var(--border)",
              }}
              role="img"
              aria-label={`${number(d.location_units)} ubicaciones: ${segments.map((s) => `${s.value} ${s.name}`).join(", ")}`}
            >
              <div>
                <strong>{number(d.location_units)}</strong>
                <span>ubicaciones</span>
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
        <section className="review-callout">
          <span className="callout-icon">
            <ClipboardCheck size={24} aria-hidden="true" />
          </span>
          <div className="eyebrow">REVISIÓN CON EVIDENCIA</div>
          <h2>
            La calidad también
            <br />
            se construye al revisar.
          </h2>
          <p>
            {number(d.review_open)} pendientes en total. La bandeja distingue
            decisiones accionables, referencias pendientes y datos por
            completar.
          </p>
          <Link to="/review" className="button light">
            Abrir bandeja de revisión
            <ArrowRight size={17} aria-hidden="true" />
          </Link>
        </section>
      </div>
      <section className="panel">
        <div className="panel-heading">
          <div>
            <h2>Procesamientos recientes</h2>
            <p>Archivos, avances y resultados en un solo lugar</p>
          </div>
          <ViewLink to="/runs">Ver todos</ViewLink>
        </div>
        <RunTable runs={d.recent_runs} />
      </section>
      <div className="method-note">
        <ShieldNote />
        <span>
          <strong>Una coordenada requiere contexto.</strong> GeoPol conserva el
          método y la precisión espacial, y separa las ubicaciones sin evidencia
          suficiente.
        </span>
        <Link to="/rules">
          Conocer la metodología
          <ArrowRight size={16} aria-hidden="true" />
        </Link>
      </div>
    </>
  );
}
function ShieldNote() {
  return <MapPin size={24} aria-hidden="true" />;
}
