import { useQuery } from "@tanstack/react-query";
import { CheckCircle2 } from "lucide-react";
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
        title="Reglas y metodología"
        actions={
          query.data && (
            <span className="version-chip">Versión {query.data.version}</span>
          )
        }
      />
      {query.isPending ? (
        <Loading />
      ) : query.isError ? (
        <ErrorNotice error={query.error} />
      ) : (
        <>
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
