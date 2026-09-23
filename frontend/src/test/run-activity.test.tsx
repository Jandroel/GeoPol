import { act, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { RunActivity } from "../components/RunActivity";
import type { Run } from "../types";

const base: Run = {
  id: "activity-synthetic",
  name: "Prueba de actividad",
  status: "PROCESSING",
  filename: "PNP_sintetico.xlsx",
  created_at: "2026-09-23T12:00:00",
  // These cumulative values must not become progress for a later stage.
  started_at: "2026-09-23T12:00:00",
  location_units: 1000,
  processed_units: 1000,
  source_rows: 3000,
  issue_rows: 0,
  rules_version: "test",
  config: { workflow: "quality_v1" },
  counts: {},
  activity: {
    job_id: "stage-job",
    status: "RUNNING",
    phase: "resolution",
    stage: "block",
    queued_at: "2026-09-23T12:04:40",
    started_at: "2026-09-23T12:05:00",
    finished_at: null,
    processed_units: 15,
    total_units: 100,
    source_rows: 3000,
    worker_online: true,
  },
};

beforeEach(() => {
  vi.useFakeTimers();
  vi.setSystemTime(new Date("2026-09-23T12:06:00Z"));
});
afterEach(() => {
  vi.useRealTimers();
});

describe("actual job activity", () => {
  it("shows the file, stage, actual elapsed time and current stage progress", () => {
    render(<RunActivity run={base} />);
    expect(screen.getByText("PNP_sintetico.xlsx")).toBeVisible();
    expect(screen.getByText("Etapa · Cuadras")).toBeVisible();
    expect(screen.getByRole("timer")).toHaveTextContent("00:01:00");
    expect(screen.getByRole("timer")).toHaveAttribute("aria-live", "off");
    expect(screen.getByRole("progressbar")).toHaveAttribute(
      "aria-valuenow",
      "15",
    );
    expect(
      screen.getByText("15 de 100 ubicaciones evaluadas en esta etapa"),
    ).toBeVisible();
    act(() => vi.advanceTimersByTime(2000));
    expect(screen.getByRole("timer")).toHaveTextContent("00:01:02");
  });

  it("stops the clock at the actual job completion and releases its interval", () => {
    const { rerender, unmount } = render(<RunActivity run={base} />);
    expect(vi.getTimerCount()).toBe(1);
    rerender(
      <RunActivity
        run={{
          ...base,
          status: "COMPLETED",
          activity: {
            ...base.activity!,
            status: "COMPLETED",
            phase: "completed",
            finished_at: "2026-09-23T12:05:45Z",
          },
        }}
      />,
    );
    expect(screen.getByRole("timer")).toHaveTextContent("00:00:45");
    expect(screen.getByText("Etapa completada")).toBeVisible();
    expect(screen.queryByRole("progressbar")).not.toBeInTheDocument();
    expect(vi.getTimerCount()).toBe(0);
    act(() => vi.advanceTimersByTime(10000));
    expect(screen.getByRole("timer")).toHaveTextContent("00:00:45");
    unmount();
    expect(vi.getTimerCount()).toBe(0);
  });

  it("counts queue waiting separately without reusing an earlier stage's progress", () => {
    render(
      <RunActivity
        run={{
          ...base,
          status: "QUEUED",
          activity: {
            ...base.activity!,
            status: "QUEUED",
            phase: "queued",
            started_at: null,
            processed_units: null,
            total_units: null,
          },
        }}
      />,
    );
    expect(screen.getByText("Tiempo en cola")).toBeVisible();
    expect(screen.getByRole("timer")).toHaveTextContent("00:01:20");
    expect(screen.getByRole("progressbar")).not.toHaveAttribute(
      "aria-valuenow",
    );
    expect(screen.queryByText("100 %")).not.toBeInTheDocument();
    act(() => vi.advanceTimersByTime(1000));
    expect(screen.getByRole("timer")).toHaveTextContent("00:01:21");
  });

  it("does not manufacture a percentage while reading rows", () => {
    render(
      <RunActivity
        run={{
          ...base,
          status: "INGESTING",
          activity: {
            ...base.activity!,
            phase: "ingestion",
            total_units: 1000,
            processed_units: 1000,
          },
        }}
      />,
    );
    expect(
      screen.getByRole("heading", { name: "Leyendo el archivo Excel" }),
    ).toBeVisible();
    expect(screen.getByRole("progressbar")).not.toHaveAttribute(
      "aria-valuenow",
    );
    expect(screen.queryByText("100 %")).not.toBeInTheDocument();
  });

  it("does not round unfinished work up to one hundred percent", () => {
    render(
      <RunActivity
        run={{
          ...base,
          activity: {
            ...base.activity!,
            processed_units: 9996,
            total_units: 10000,
          },
        }}
      />,
    );
    expect(screen.getByText("99.9 %")).toBeVisible();
    expect(screen.queryByText("100 %")).not.toBeInTheDocument();
    expect(
      Number(screen.getByRole("progressbar").getAttribute("aria-valuenow")),
    ).toBeCloseTo(99.96);
  });

  it("shows unknown time and progress for legacy jobs without activity metadata", () => {
    render(<RunActivity run={{ ...base, activity: undefined }} />);
    expect(screen.getByRole("timer")).toHaveTextContent("Tiempo no disponible");
    expect(screen.getByRole("progressbar")).not.toHaveAttribute(
      "aria-valuenow",
    );
    expect(screen.queryByText("100 %")).not.toBeInTheDocument();
  });

  it("does not let a completed job with a missing end time keep counting", () => {
    render(
      <RunActivity
        run={{
          ...base,
          status: "COMPLETED",
          activity: {
            ...base.activity!,
            status: "COMPLETED",
            phase: "completed",
            finished_at: null,
          },
        }}
      />,
    );
    expect(screen.getByRole("timer")).toHaveTextContent("Tiempo no disponible");
    expect(vi.getTimerCount()).toBe(0);
  });

  it("distinguishes an error from an in-progress job and preserves the cause", () => {
    render(
      <RunActivity
        run={{
          ...base,
          status: "FAILED",
          error: "Archivo no disponible",
          activity: {
            ...base.activity!,
            status: "FAILED",
            phase: "failed",
            finished_at: "2026-09-23T12:05:30Z",
          },
        }}
      />,
    );
    expect(
      screen.getByRole("heading", {
        name: "El procesamiento necesita atención",
      }),
    ).toBeVisible();
    expect(screen.getByRole("alert")).toHaveTextContent(
      "Archivo no disponible",
    );
    expect(screen.getByRole("timer")).toHaveTextContent("00:00:30");
    expect(vi.getTimerCount()).toBe(0);
  });

  it("indicates a disconnected worker without claiming an estimated completion", () => {
    render(
      <RunActivity
        run={{
          ...base,
          status: "QUEUED",
          activity: {
            ...base.activity!,
            status: "QUEUED",
            phase: "queued",
            worker_online: false,
          },
        }}
      />,
    );
    expect(
      screen.getByText(/No se recibe una señal reciente del servicio/),
    ).toBeVisible();
    expect(screen.queryByText(/tiempo restante/i)).not.toBeInTheDocument();
  });

  it("keeps cancellation terminal and does not display zero-of-zero as complete", () => {
    const { rerender } = render(
      <RunActivity
        run={{
          ...base,
          activity: {
            ...base.activity!,
            processed_units: 0,
            total_units: 0,
          },
        }}
      />,
    );
    expect(screen.getByRole("progressbar")).not.toHaveAttribute(
      "aria-valuenow",
    );
    rerender(
      <RunActivity
        run={{
          ...base,
          status: "CANCELLED",
          activity: {
            ...base.activity!,
            status: "CANCELLED",
            phase: "cancelled",
            finished_at: "2026-09-23T12:05:10Z",
          },
        }}
      />,
    );
    expect(screen.getByText("Procesamiento cancelado")).toBeVisible();
    expect(screen.getByRole("timer")).toHaveTextContent("00:00:10");
    expect(vi.getTimerCount()).toBe(0);
  });
});
