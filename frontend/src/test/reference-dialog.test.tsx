import {
  act,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useState } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ReferenceExcelCards } from "../components/ReferenceExcelCards";
import { post } from "../lib/api";
import { uploadFile } from "../lib/upload";
import type { Reference, ReferenceExcelKind, Upload } from "../types";

vi.mock("../auth", () => ({
  useAuth: () => ({ user: { id: "dialog-qa", role: "admin" } }),
}));
vi.mock("../lib/api", () => ({ post: vi.fn() }));
vi.mock("../lib/upload", () => ({
  uploadFile: vi.fn(),
  getResume: () => null,
  clearResume: vi.fn(),
}));

const catalog: Reference = {
  id: "dialog-catalog",
  name: "Puertas QA",
  version: "v1",
  source: "QA",
  feature_count: 1,
  sha256: "qa",
  kinds: ["door"],
};
const profile = {
  columns: ["UBIGEO", "NOMVIA"],
  sheets: ["Puertas"],
  sheet: "Puertas",
  suggested_mapping: { ubigeo: "UBIGEO", street_name: "NOMVIA" },
  warnings: [],
};
const onBusy = vi.fn();
function Harness() {
  const [selected, setSelected] = useState<
    Partial<Record<ReferenceExcelKind, string>>
  >({});
  const [catalogs, setCatalogs] = useState<Reference[]>([]);
  return (
    <ReferenceExcelCards
      editorMode="dialog"
      catalogs={catalogs}
      selected={selected}
      onSelect={(kind, id) => {
        setSelected({ [kind]: id });
        setCatalogs([catalog]);
      }}
      onBusy={onBusy}
    />
  );
}
function setup() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 } },
  });
  render(
    <QueryClientProvider client={client}>
      <Harness />
    </QueryClientProvider>,
  );
  return userEvent.setup();
}
beforeEach(() => {
  vi.clearAllMocks();
  document.body.style.overflow = "auto";
});
afterEach(() => {
  document.body.style.overflow = "";
});

describe("Reference editor dialog", () => {
  it("keeps one mounted file input and returns focus after close and Escape cancellation", async () => {
    const user = setup();
    const trigger = screen.getByRole("button", {
      name: "Configurar referencia: Puertas / viviendas",
    });
    await user.click(trigger);
    const dialog = screen.getByRole("dialog", {
      name: "Configurar Puertas / viviendas",
    });
    const close = within(dialog).getByRole("button", {
      name: "Cerrar configuración de Puertas / viviendas",
    });
    expect(close).toHaveFocus();
    expect(document.body.style.overflow).toBe("hidden");
    const input = within(dialog).getByLabelText(
      "Archivo Excel · Puertas / viviendas",
    ) as HTMLInputElement;
    const file = new File(["qa"], "puertas.xlsx", {
      type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    });
    await user.upload(input, file);
    await user.click(close);
    expect(dialog).not.toHaveAttribute("open");
    expect(trigger).toHaveFocus();
    expect(document.body.style.overflow).toBe("auto");
    await user.click(trigger);
    expect(
      within(dialog).getByLabelText("Archivo Excel · Puertas / viviendas"),
    ).toBe(input);
    expect(input.files?.[0]).toBe(file);
    expect(
      within(dialog).getByRole("button", {
        name: "Leer columnas de referencia",
      }),
    ).toBeEnabled();
    fireEvent(
      dialog,
      new Event("cancel", { bubbles: false, cancelable: true }),
    );
    expect(trigger).toHaveAttribute("aria-expanded", "false");
    expect(trigger).toHaveFocus();
  });

  it("continues loading while closed, preserves mapping drafts and stays open after saving", async () => {
    let finishUpload!: (upload: Upload) => void;
    vi.mocked(uploadFile).mockImplementation(
      () =>
        new Promise((resolve) => {
          finishUpload = resolve;
        }),
    );
    vi.mocked(post).mockImplementation(async (path) =>
      path.endsWith("/preview") ? profile : catalog,
    );
    const user = setup();
    const trigger = screen.getByRole("button", {
      name: "Configurar referencia: Puertas / viviendas",
    });
    await user.click(trigger);
    const dialog = screen.getByRole("dialog", {
      name: "Configurar Puertas / viviendas",
    });
    const close = within(dialog).getByRole("button", {
      name: "Cerrar configuración de Puertas / viviendas",
    });
    await user.upload(
      within(dialog).getByLabelText("Archivo Excel · Puertas / viviendas"),
      new File(["qa"], "puertas.xlsx"),
    );
    await user.click(
      within(dialog).getByRole("button", {
        name: "Leer columnas de referencia",
      }),
    );
    expect(onBusy).toHaveBeenLastCalledWith("doors", true);
    await user.click(close);
    expect(trigger).toHaveTextContent("Procesando…");
    await act(async () =>
      finishUpload({
        id: "dialog-upload",
        filename: "puertas.xlsx",
        size: 2,
        offset: 2,
        status: "COMPLETE",
      }),
    );
    await waitFor(() =>
      expect(onBusy).toHaveBeenLastCalledWith("doors", false),
    );
    await user.click(trigger);
    expect(
      within(dialog).getByLabelText("Nombre de vía", { exact: true }),
    ).toHaveValue("NOMVIA");
    await user.type(
      within(dialog).getByLabelText("Versión de la fuente"),
      "v1",
    );
    await user.click(close);
    await user.click(trigger);
    expect(within(dialog).getByLabelText("Versión de la fuente")).toHaveValue(
      "v1",
    );
    await user.click(
      within(dialog).getByRole("button", {
        name: "Guardar y utilizar referencia",
      }),
    );
    await waitFor(() =>
      expect(
        within(dialog).getByRole("status", {
          name: "Disponibilidad de la referencia",
        }),
      ).toHaveTextContent("1 elementos disponibles"),
    );
    expect(dialog).toHaveAttribute("open");
    expect(trigger).toHaveAttribute("aria-expanded", "true");
  });

  it("dismisses a backdrop click without dismissing clicks inside the editor", async () => {
    const user = setup();
    const trigger = screen.getByRole("button", {
      name: "Configurar referencia: Puertas / viviendas",
    });
    await user.click(trigger);
    const dialog = screen.getByRole("dialog", {
      name: "Configurar Puertas / viviendas",
    });
    vi.spyOn(dialog, "getBoundingClientRect").mockReturnValue({
      left: 100,
      top: 100,
      right: 600,
      bottom: 700,
      width: 500,
      height: 600,
      x: 100,
      y: 100,
      toJSON: () => ({}),
    });
    fireEvent.pointerDown(dialog, { clientX: 150, clientY: 150 });
    fireEvent.click(dialog, { clientX: 150, clientY: 150 });
    expect(dialog).toHaveAttribute("open");
    fireEvent.pointerDown(dialog, { clientX: 10, clientY: 10 });
    fireEvent.click(dialog, { clientX: 10, clientY: 10 });
    expect(dialog).not.toHaveAttribute("open");
    expect(trigger).toHaveFocus();
  });
});
