import { PageHeader } from "../components/ui";
import { ResultsTable } from "../components/ResultsTable";
export function Review() {
  return (
    <>
      <PageHeader
        eyebrow="CONTROL DE CALIDAD"
        title="Revisión de ubicaciones"
        description="Examina la evidencia, compara candidatos y registra una decisión trazable."
      />
      <ResultsTable review />
    </>
  );
}
