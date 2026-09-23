import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ExportPanel } from "../components/ExportPanel";
import { downloadAuthenticated, post, request } from "../lib/api";
import type { ExportJob } from "../types";

const auth = vi.hoisted(() => ({
  user: { id: "synthetic-export-user", role: "admin" },
}));
vi.mock("../auth", () => ({ useAuth: () => auth }));
vi.mock("../lib/api", () => ({
  post: vi.fn(),
  request: vi.fn(),
  downloadAuthenticated: vi.fn(),
}));

const storageKey = "geopol.export.synthetic-export-user.synthetic-run";
function setup(
  job: Partial<ExportJob> = {},
  scope: {
    qualityFlag?: number;
    qualityStage?: string;
    reviewState?: string;
    allowCumulative?: boolean;
  } = {},
) {
  const completed: ExportJob = {
    id: "synthetic-export",
    status: "COMPLETED",
    format: "xlsx",
    filename: "synthetic.xlsx",
    row_count: 2,
    ...job,
  };
  vi.mocked(post).mockResolvedValue(completed);
  vi.mocked(request).mockResolvedValue(completed);
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 } },
  });
  render(
    <QueryClientProvider client={client}>
      <ExportPanel runId="synthetic-run" {...scope} />
    </QueryClientProvider>,
  );
  return userEvent.setup();
}

beforeEach(() => {
  vi.clearAllMocks();
  localStorage.clear();
  auth.user.role = "admin";
});

describe("spreadsheet export formats", () => {
  it("can export a selected quality or the complete updated workbook without carrying the filter", async () => {
    const user = setup(
      {},
      {
        qualityFlag: 1,
        qualityStage: "door",
        reviewState: "quick_review",
        allowCumulative: true,
      },
    );
    await user.click(
      screen.getByRole("button", { name: "Preparar exportación" }),
    );
    await screen.findByRole("button", { name: "Descargar Excel" });
    expect(post).toHaveBeenLastCalledWith("/runs/synthetic-run/exports", {
      profile: "locations",
      format: "xlsx",
      safe_spreadsheet: true,
      quality_flag: 1,
      review_state: "quick_review",
      quality_stage: "door",
    });
    await user.click(
      screen.getByRole("checkbox", { name: /Exportar el acumulado completo/ }),
    );
    expect(
      screen.queryByRole("button", { name: "Descargar Excel" }),
    ).not.toBeInTheDocument();
    await user.click(
      screen.getByRole("button", { name: "Preparar exportación" }),
    );
    await waitFor(() =>
      expect(post).toHaveBeenLastCalledWith("/runs/synthetic-run/exports", {
        profile: "locations",
        format: "xlsx",
        safe_spreadsheet: true,
      }),
    );
  });
  it("defaults to Excel and requests a protected XLSX for the selected profile", async () => {
    const user = setup();
    expect(screen.getByLabelText("Formato del archivo")).toHaveValue("xlsx");
    expect(
      screen.getByLabelText("Formato del archivo"),
    ).toHaveAccessibleDescription(
      "Excel con columnas ajustadas, filtros, encabezados fijos y colores INEI.",
    );
    await user.click(
      screen.getByRole("button", { name: "Preparar exportación" }),
    );
    await screen.findByRole("button", { name: "Descargar Excel" });
    expect(post).toHaveBeenCalledWith("/runs/synthetic-run/exports", {
      profile: "locations",
      format: "xlsx",
      safe_spreadsheet: true,
    });
    expect(localStorage.getItem(storageKey)).toBe("synthetic-export");
  });

  it("lets an authorized operator explicitly choose CSV and source rows", async () => {
    auth.user.role = "operator";
    const user = setup({ format: "csv", filename: "synthetic.csv" });
    await user.selectOptions(
      screen.getByLabelText("Formato del archivo"),
      "csv",
    );
    await user.selectOptions(
      screen.getByLabelText("Perfil de exportación"),
      "source_rows",
    );
    await user.click(
      screen.getByRole("button", { name: "Preparar exportación" }),
    );
    await screen.findByRole("button", { name: "Descargar CSV" });
    expect(post).toHaveBeenCalledWith("/runs/synthetic-run/exports", {
      profile: "source_rows",
      format: "csv",
      safe_spreadsheet: true,
    });
  });

  it("keeps the completed download format when the next export selection changes", async () => {
    const user = setup();
    await user.click(
      screen.getByRole("button", { name: "Preparar exportación" }),
    );
    const download = await screen.findByRole("button", {
      name: "Descargar Excel",
    });
    await user.selectOptions(
      screen.getByLabelText("Formato del archivo"),
      "csv",
    );
    await user.click(download);
    await waitFor(() =>
      expect(downloadAuthenticated).toHaveBeenCalledWith(
        "/exports/synthetic-export/download",
        "synthetic.xlsx",
      ),
    );
    expect(
      screen.queryByRole("button", { name: "Descargar CSV" }),
    ).not.toBeInTheDocument();
  });

  it("restores a legacy CSV job without mislabeling it as the default Excel format", async () => {
    localStorage.setItem(storageKey, "legacy-export");
    const user = setup({
      id: "legacy-export",
      format: undefined,
      filename: "legacy.csv",
    });
    const download = await screen.findByRole("button", {
      name: "Descargar CSV",
    });
    expect(screen.getByLabelText("Formato del archivo")).toHaveValue("xlsx");
    await user.click(download);
    await waitFor(() =>
      expect(downloadAuthenticated).toHaveBeenCalledWith(
        "/exports/legacy-export/download",
        "legacy.csv",
      ),
    );
    expect(post).not.toHaveBeenCalled();
  });

  it("does not offer original source columns to an analyst", () => {
    auth.user.role = "analyst";
    setup();
    expect(
      screen.queryByRole("option", { name: /Filas originales/ }),
    ).not.toBeInTheDocument();
  });
});
