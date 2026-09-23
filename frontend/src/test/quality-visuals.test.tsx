import { fireEvent, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { StageChart } from "../components/StageChart";
import { QualityProgressCard } from "../components/QualityProgressCard";
import type { QualityOverview } from "../types";

const stage: QualityOverview["stages"][number] = {
  key: "door",
  label: "Puertas",
  units: 10,
  source_rows: 25,
  resolved: 2,
  review: 3,
  unmatched: 4,
  blocked: 1,
  percent_of_total: 50,
};
const summary: QualityOverview = {
  run_id: "synthetic-run",
  workflow: "quality_v1",
  policy_version: "quality-v1",
  provisional: false,
  totals: {
    units: 20,
    source_rows: 45,
    resolved: 4,
    review: 6,
    unmatched: 8,
    blocked: 2,
    unprocessed: 0,
  },
  qualities: [],
  flags: [],
  review_states: [],
  stages: [stage],
  can_advance: true,
  next_stage: "block",
  eligible_units: 8,
  held_review_units: 6,
};

describe("interactive stage distributions", () => {
  it("explores the historical denominator with the keyboard and keeps a selected category until cleared", async () => {
    const user = userEvent.setup();
    const { container } = render(<StageChart stage={stage} />);
    const resolved = screen.getByRole("button", {
      name: /Resueltos: 2 de 10, 20 %/,
    });
    await user.tab();
    expect(resolved).toHaveFocus();
    expect(
      screen.getByText("Resueltos: 2 de 10 evaluadas en esta etapa (20 %)."),
    ).toBeInTheDocument();
    expect(container.querySelector('[data-category="resolved"]')).toHaveClass(
      "is-highlighted",
    );
    await user.keyboard("{Enter}");
    expect(resolved).toHaveAttribute("aria-pressed", "true");
    await user.tab();
    expect(
      screen.getByText("Por revisar: 3 de 10 evaluadas en esta etapa (30 %)."),
    ).toBeInTheDocument();
    await user.keyboard(" ");
    expect(
      screen.getByRole("button", { name: /Por revisar: 3 de 10/ }),
    ).toHaveAttribute("aria-pressed", "true");
    expect(resolved).toHaveAttribute("aria-pressed", "false");
    await user.keyboard("{Escape}");
    expect(
      screen.getByText(
        "Base del gráfico: 10 ubicaciones evaluadas en esta etapa.",
      ),
    ).toBeInTheDocument();
    expect(
      container.querySelectorAll(".stage-ring-segment.is-highlighted"),
    ).toHaveLength(0);
  });
  it("shows pointer details on SVG and touch-friendly legend selection without changing the counts", async () => {
    const user = userEvent.setup();
    const { container } = render(<StageChart stage={stage} />);
    const segment = container.querySelector('[data-category="unmatched"]')!;
    fireEvent.mouseEnter(segment);
    expect(container.querySelector(".stage-ring-value")).toHaveTextContent(
      "440 %sin coincidencia",
    );
    expect(
      screen.getByText(
        "Sin coincidencia: 4 de 10 evaluadas en esta etapa (40 %).",
      ),
    ).toBeInTheDocument();
    fireEvent.mouseLeave(segment);
    expect(container.querySelector(".stage-ring-value")).toHaveTextContent(
      "10evaluadas",
    );
    const table = screen.getByRole("table", {
      name: /Distribución de Puertas/,
    });
    const pending = within(table).getByRole("button", {
      name: /Referencia o datos pendientes/,
    });
    await user.click(pending);
    await user.unhover(pending);
    expect(pending).toHaveAttribute("aria-pressed", "true");
    expect(
      screen.getByText(
        "Referencia o datos pendientes: 1 de 10 evaluadas en esta etapa (10 %).",
      ),
    ).toBeInTheDocument();
    expect(
      within(table).getByRole("row", { name: /Sin coincidencia/ }),
    ).toHaveTextContent("40 %");
    await user.click(screen.getByRole("button", { name: "Ver total" }));
    expect(pending).toHaveAttribute("aria-pressed", "false");
    expect(
      screen.getByText(
        "Base del gráfico: 10 ubicaciones evaluadas en esta etapa.",
      ),
    ).toBeInTheDocument();
  });
  it("represents an unevaluated stage without invented progress or NaN percentages", async () => {
    const empty = {
      ...stage,
      units: 0,
      resolved: 0,
      review: 0,
      unmatched: 0,
      blocked: 0,
      source_rows: 0,
    };
    const { container } = render(<StageChart stage={empty} />);
    expect(
      screen.getByText("Esta etapa aún no tiene ubicaciones evaluadas."),
    ).toBeInTheDocument();
    expect(container.querySelectorAll(".stage-ring-segment")).toHaveLength(0);
    expect(screen.getByRole("table")).not.toHaveTextContent("NaN");
    expect(screen.getByRole("button", { name: "Ver total" })).toBeDisabled();
  });
});

describe("quality progress summary", () => {
  it("uses current resolved units, separately identifies original rows, and advances only after a deliberate click", async () => {
    const user = userEvent.setup();
    const advance = vi.fn();
    render(
      <QualityProgressCard
        data={summary}
        active={false}
        busy={false}
        canManage
        superseded={false}
        onAdvance={advance}
      />,
    );
    expect(
      screen.getByRole("progressbar", { name: "Ubicaciones resueltas" }),
    ).toHaveAttribute("aria-valuenow", "4");
    expect(screen.getByRole("progressbar")).toHaveAttribute(
      "aria-valuemax",
      "20",
    );
    expect(screen.getByRole("progressbar")).toHaveAttribute(
      "aria-valuetext",
      "4 de 20 ubicaciones resueltas (20 %)",
    );
    expect(
      screen.getByText("El archivo original contiene 45 filas."),
    ).toBeInTheDocument();
    expect(advance).not.toHaveBeenCalled();
    await user.click(
      screen.getByRole("button", { name: "Continuar con cuadras" }),
    );
    expect(advance).toHaveBeenCalledWith("block");
  });
  it("keeps the progression unavailable during a running stage and does not invent success for an empty run", () => {
    const { rerender } = render(
      <QualityProgressCard
        data={summary}
        active
        busy={false}
        canManage
        superseded={false}
        onAdvance={vi.fn()}
      />,
    );
    expect(
      screen.queryByRole("button", { name: "Continuar con cuadras" }),
    ).not.toBeInTheDocument();
    expect(screen.getByText("Procesamiento activo")).toBeInTheDocument();
    expect(
      screen.getByRole("heading", { name: "Evaluando ubicaciones" }),
    ).toBeInTheDocument();
    expect(screen.queryByText(/ubicaciones elegibles/)).not.toBeInTheDocument();
    rerender(
      <QualityProgressCard
        data={{ ...summary, next_stage: null }}
        active
        busy={false}
        canManage
        superseded={false}
        onAdvance={vi.fn()}
      />,
    );
    expect(
      screen.getByRole("heading", { name: "Evaluando ubicaciones" }),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole("heading", { name: "Sin otra etapa disponible" }),
    ).not.toBeInTheDocument();
    rerender(
      <QualityProgressCard
        data={{
          ...summary,
          totals: { ...summary.totals, units: 0, resolved: 0 },
          next_stage: null,
        }}
        active={false}
        busy={false}
        canManage
        superseded={false}
        onAdvance={vi.fn()}
      />,
    );
    expect(
      screen.getByRole("heading", { name: "Sin otra etapa disponible" }),
    ).toBeInTheDocument();
    expect(screen.getByRole("progressbar")).toHaveAttribute(
      "aria-valuenow",
      "0",
    );
  });
});
