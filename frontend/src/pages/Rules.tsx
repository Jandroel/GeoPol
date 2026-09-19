import { useQuery } from "@tanstack/react-query";
import { BookOpen, CheckCircle2 } from "lucide-react";
import { request } from "../lib/api";
import { ErrorNotice, Loading, PageHeader } from "../components/ui";
interface RulesData {
  version: string;
  policies: { name: string; description: string }[];
  limitations: string[];
}
export function Rules() {
  const query = useQuery({
    queryKey: ["rules"],
    queryFn: () => request<RulesData>("/rules"),
  });
  return (
    <>
      <PageHeader
        eyebrow="CRITERIOS EXPLÍCITOS"
        title="Reglas y metodología"
        description="Conoce cómo se interpreta una dirección y qué puede afirmar un resultado."
      />
      {query.isPending ? (
        <Loading />
      ) : query.isError ? (
        <ErrorNotice error={query.error} />
      ) : (
        <>
          <section className="methodology-hero">
            <BookOpen size={35} aria-hidden="true" />
            <div>
              <div className="eyebrow">
                REGLAS VERSIONADAS · {query.data.version}
              </div>
              <h2>La ubicación es una conclusión documentada.</h2>
              <p>
                La resolución, el método, la precisión y la evidencia se
                conservan de forma independiente en cada resultado.
              </p>
            </div>
          </section>
          <div className="rules-grid">
            {query.data.policies.map((policy, i) => (
              <article className="panel policy" key={i}>
                <span className="policy-number">
                  {String(i + 1).padStart(2, "0")}
                </span>
                <h2>{policy.name}</h2>
                <p>{policy.description}</p>
              </article>
            ))}
          </div>
          <section className="panel form-panel">
            <h2>Alcance y límites de este MVP</h2>
            <ul className="limitation-list">
              {query.data.limitations.map((l, i) => (
                <li key={i}>
                  <CheckCircle2 size={18} aria-hidden="true" />
                  <span>{l}</span>
                </li>
              ))}
            </ul>
          </section>
        </>
      )}
    </>
  );
}
