import { ArrowRight } from "lucide-react";
import { Link } from "react-router-dom";
import { PageHeader } from "../components/ui";
import { useAuth } from "../auth";
import { NewRun } from "./NewRun";
import "./intake-workspace.css";
import "./overview.css";

export function Dashboard() {
  const { user } = useAuth();
  const allowed = ["admin", "operator"].includes(user?.role ?? "");
  return (
    <div className="overview-page">
      <PageHeader title="Vista general" />
      <section
        className="overview-introduction"
        aria-label="Carga de archivos de GeoPol"
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
          <div className="overview-intro-copy">
            <h2>Geocodificación de hechos delictivos</h2>
            <p>
              Carga el archivo de SIDPOL y selecciona las referencias para
              contrastar sus direcciones.
            </p>
          </div>
          <div className="overview-imports">
            {allowed ? (
              <NewRun mode="overview" />
            ) : (
              <section className="overview-readonly">
                <h3>Consulta de información</h3>
                <p>
                  Tu perfil permite consultar resultados y documentación. La
                  carga de archivos está disponible para operadores y
                  administradores.
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
      </section>
    </div>
  );
}
