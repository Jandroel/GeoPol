import { useQuery } from "@tanstack/react-query";
import { ArrowRight, MapPinned, BookOpen } from "lucide-react";
import { Link } from "react-router-dom";
import { request } from "../lib/api";
import { number } from "../lib/format";
import type { Dashboard as DashboardData } from "../types";
import { ErrorNotice, Loading, PageHeader, ViewLink } from "../components/ui";
import { RunTable } from "../components/RunTable";
import { useAuth } from "../auth";
import { NewRun } from "./NewRun";
import "./intake-workspace.css";
import "./overview.css";

export function Dashboard() {
  const { user } = useAuth();
  const data = useQuery({
    queryKey: ["dashboard"],
    queryFn: () => request<DashboardData>("/dashboard"),
    refetchInterval: 15000,
  });
  const allowed = ["admin", "operator"].includes(user?.role ?? "");
  const d = data.data;
  return (
    <>
      <PageHeader
        title="Vista general"
        description="Carga la información de SIDPOL y las referencias censales para comenzar."
      />
      <div className="overview-workspace">
        <section
          className="overview-introduction"
          aria-label="GeoPol y resumen operativo"
        >
          <img
            className="overview-artwork"
            src="/images/peru-geospatial.png"
            alt=""
            aria-hidden="true"
            width="1086"
            height="1448"
            decoding="async"
          />
          <div className="overview-hero-content">
            <div className="overview-identity">
              <MapPinned size={36} strokeWidth={1.5} aria-hidden="true" />
              <span>
                GeoPol <small>INEI · Información geoespacial</small>
              </span>
            </div>
            <div className="overview-intro-copy">
              <p className="overview-eyebrow">SIDPOL / DATACRIM + CENSOS</p>
              <h2>Geocodificación de hechos delictivos</h2>
              <p>
                Contrasta direcciones con referencias geográficas, resuelve
                coincidencias y revisa las excepciones.
              </p>
            </div>
            <div className="overview-summary">
              <h3>Estado de la información</h3>
              {data.isPending ? (
                <Loading />
              ) : data.isError ? (
                <ErrorNotice error={data.error} />
              ) : (
                d && (
                  <>
                    <dl>
                      <div>
                        <dt>Filas de origen</dt>
                        <dd>{number(d.source_rows)}</dd>
                      </div>
                      <div>
                        <dt>Ubicaciones</dt>
                        <dd>{number(d.location_units)}</dd>
                      </div>
                      <div>
                        <dt>Aceptadas</dt>
                        <dd>{number(d.accepted)}</dd>
                      </div>
                      <div>
                        <dt>Por revisar</dt>
                        <dd>{number(d.review_actionable)}</dd>
                      </div>
                    </dl>
                    <p>
                      Ejecuciones terminadas vigentes. Las filas pueden
                      corresponder a una misma ubicación.
                    </p>
                  </>
                )
              )}
              <Link to="/statistics" className="overview-statistics-link">
                Consultar estadística{" "}
                <ArrowRight size={18} aria-hidden="true" />
              </Link>
            </div>
            <Link to="/documentation" className="overview-guide-link">
              <BookOpen size={18} aria-hidden="true" /> Requisitos y guía de
              carga
            </Link>
          </div>
        </section>
        <div className="overview-intake">
          {allowed ? (
            <NewRun mode="overview" />
          ) : (
            <section className="panel overview-readonly">
              <h2>Consulta de información</h2>
              <p>
                Tu perfil permite consultar resultados y documentación. La carga
                de archivos está disponible para operadores y administradores.
              </p>
              <Link className="button primary" to="/statistics">
                Ver resultados <ArrowRight size={18} aria-hidden="true" />
              </Link>
              <Link className="button secondary" to="/procedures">
                Ver procedimientos
              </Link>
            </section>
          )}
        </div>
      </div>
      <section className="panel overview-recent">
        <div className="panel-heading">
          <div>
            <h2>Procesamientos recientes</h2>
            <p>
              {d
                ? `${number(d.runs)} en el historial`
                : "Historial de ejecuciones"}
            </p>
          </div>
          <ViewLink to="/runs">Ver todos</ViewLink>
        </div>
        {d ? (
          <RunTable runs={d.recent_runs} />
        ) : data.isPending ? (
          <Loading />
        ) : (
          <ErrorNotice error={data.error} />
        )}
      </section>
    </>
  );
}
