import {
  act,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { Layout } from "../components/Layout";

const auth = vi.hoisted(() => ({
  user: { username: "operador", role: "admin" },
  logout: vi.fn(),
}));
vi.mock("../auth", () => ({ useAuth: () => auth }));

let listeners: Array<(event: MediaQueryListEvent) => void>;
let matches = false;
function viewport(mobile: boolean) {
  matches = mobile;
  act(() =>
    listeners.forEach((listener) =>
      listener({ matches } as MediaQueryListEvent),
    ),
  );
}
function show(path = "/runs/new") {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route element={<Layout />}>
          <Route path="*" element={<button>Acción del contenido</button>} />
        </Route>
      </Routes>
    </MemoryRouter>,
  );
}

beforeEach(() => {
  localStorage.clear();
  matches = false;
  listeners = [];
  auth.user.role = "admin";
  vi.stubGlobal(
    "matchMedia",
    vi.fn(() => ({
      matches,
      addEventListener: (
        _event: string,
        listener: (event: MediaQueryListEvent) => void,
      ) => listeners.push(listener),
      removeEventListener: (
        _event: string,
        listener: (event: MediaQueryListEvent) => void,
      ) => {
        listeners = listeners.filter((value) => value !== listener);
      },
    })),
  );
});
afterEach(() => {
  vi.unstubAllGlobals();
  document.body.style.overflow = "";
});

describe("Navegación del espacio de trabajo", () => {
  it("permite contraer, conservar la preferencia y seguir navegando con nombres accesibles", async () => {
    const user = userEvent.setup();
    const view = show();
    await user.click(screen.getByRole("button", { name: "Contraer menú" }));
    expect(
      screen.getByRole("button", { name: "Expandir menú" }),
    ).toHaveAttribute("aria-expanded", "false");
    const nav = screen.getByRole("navigation", {
      name: "Navegación principal",
    });
    await user.click(
      within(nav).getByRole("link", { name: "Seguimiento por calidad" }),
    );
    expect(
      within(nav).getByRole("link", { name: "Seguimiento por calidad" }),
    ).toHaveAttribute("aria-current", "page");
    expect(
      within(
        screen.getByRole("navigation", { name: "Ubicación actual" }),
      ).getByText("Seguimiento por calidad"),
    ).toBeVisible();
    view.unmount();
    show();
    expect(screen.getByRole("button", { name: "Expandir menú" })).toBeVisible();
    await user.click(screen.getByRole("button", { name: "Expandir menú" }));
    expect(
      screen.getByRole("button", { name: "Contraer menú" }),
    ).toHaveAttribute("aria-expanded", "true");
  });

  it("mantiene el procesamiento activo en una ruta de detalle y permite volver a la lista", async () => {
    const user = userEvent.setup();
    show("/runs/example-run?tab=quality");
    const nav = screen.getByRole("navigation", {
      name: "Navegación principal",
    });
    expect(
      within(nav).getByRole("link", { name: "Procesamientos" }),
    ).toHaveAttribute("aria-current", "page");
    expect(
      within(nav).getByRole("link", { name: "Carga de archivos" }),
    ).not.toHaveAttribute("aria-current");
    const breadcrumb = screen.getByRole("navigation", {
      name: "Ubicación actual",
    });
    expect(
      within(breadcrumb).getByText("Detalle del procesamiento"),
    ).toHaveAttribute("aria-current", "page");
    await user.click(
      within(breadcrumb).getByRole("link", { name: "Procesamientos" }),
    );
    expect(
      within(breadcrumb).queryByText("Detalle del procesamiento"),
    ).not.toBeInTheDocument();
  });

  it("omite acciones no autorizadas de carga y auditoría para un revisor", () => {
    auth.user.role = "reviewer";
    show("/review");
    const nav = screen.getByRole("navigation", {
      name: "Navegación principal",
    });
    expect(
      within(nav).queryByRole("link", { name: "Carga de archivos" }),
    ).not.toBeInTheDocument();
    expect(
      within(nav).queryByRole("link", { name: "Auditoría" }),
    ).not.toBeInTheDocument();
    expect(
      within(nav).getByRole("link", { name: "Revisión de ubicaciones" }),
    ).toHaveAttribute("aria-current", "page");
  });

  it("retiene el foco dentro del menú móvil y lo devuelve al botón al cerrar con Escape", async () => {
    viewport(true);
    document.body.style.overflow = "auto";
    const user = userEvent.setup();
    show();
    const opener = screen.getByRole("button", { name: "Abrir navegación" });
    await user.click(opener);
    const drawer = screen.getByRole("dialog", { name: "Menú de navegación" });
    expect(drawer).toHaveAttribute("aria-modal", "true");
    expect(document.body.style.overflow).toBe("hidden");
    await waitFor(() =>
      expect(
        within(drawer).getByRole("button", { name: "Cerrar navegación" }),
      ).toHaveFocus(),
    );
    const first = within(drawer).getByRole("link", {
      name: "GeoPol, vista general",
    });
    const last = within(drawer).getByRole("link", { name: "Auditoría" });
    first.focus();
    fireEvent.keyDown(document, { key: "Tab", shiftKey: true });
    expect(last).toHaveFocus();
    fireEvent.keyDown(document, { key: "Tab" });
    expect(first).toHaveFocus();
    await user.keyboard("{Escape}");
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(document.body.style.overflow).toBe("auto");
    expect(opener).toHaveFocus();
  });

  it("cierra el drawer al elegir una página y libera la navegación al pasar a escritorio", async () => {
    viewport(true);
    const user = userEvent.setup();
    show();
    await user.click(screen.getByRole("button", { name: "Abrir navegación" }));
    await user.click(
      within(screen.getByRole("dialog")).getByRole("link", {
        name: "Procesamientos",
      }),
    );
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(document.body.style.overflow).toBe("");
    await user.click(screen.getByRole("button", { name: "Abrir navegación" }));
    viewport(false);
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "Abrir navegación" }),
    ).not.toBeInTheDocument();
    expect(document.body.style.overflow).toBe("");
    screen.getByRole("button", { name: "Acción del contenido" }).focus();
    await user.tab();
    expect(
      screen.getByRole("button", { name: "Acción del contenido" }),
    ).not.toHaveFocus();
    expect(screen.getByRole("button", { name: "Contraer menú" })).toBeVisible();
  });

  it("el fondo del drawer permite cerrarlo sin activar el contenido", async () => {
    viewport(true);
    const user = userEvent.setup();
    show();
    await user.click(screen.getByRole("button", { name: "Abrir navegación" }));
    const scrim = screen
      .getAllByRole("button", { name: "Cerrar navegación" })
      .find((button) => button.tabIndex === -1);
    expect(scrim).toBeDefined();
    await user.click(scrim!);
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(document.body.style.overflow).toBe("");
  });

  it("enfoca al abrir después de plegar y cambiar de breakpoint sin esperar frames", () => {
    show("/runs/example-run");
    fireEvent.click(screen.getByRole("button", { name: "Contraer menú" }));
    fireEvent.click(screen.getByRole("button", { name: "Expandir menú" }));
    viewport(true);
    fireEvent.click(screen.getByRole("button", { name: "Abrir navegación" }));
    const drawer = screen.getByRole("dialog", { name: "Menú de navegación" });
    expect(drawer).not.toHaveAttribute("inert");
    expect(
      within(drawer).getByRole("button", { name: "Cerrar navegación" }),
    ).toHaveFocus();
    fireEvent.keyDown(document, { key: "Escape" });
    expect(
      screen.getByRole("button", { name: "Abrir navegación" }),
    ).toHaveFocus();
    viewport(false);
    viewport(true);
    fireEvent.click(screen.getByRole("button", { name: "Abrir navegación" }));
    expect(
      within(screen.getByRole("dialog")).getByRole("button", {
        name: "Cerrar navegación",
      }),
    ).toHaveFocus();
  });

  it("espera a que el control sea visible y cancela el foco pendiente si se cierra", async () => {
    viewport(true);
    show();
    const close = document.querySelector<HTMLButtonElement>(".mobile-close")!;
    const opener = screen.getByRole("button", { name: "Abrir navegación" });
    close.style.visibility = "hidden";
    fireEvent.click(opener);
    expect(close).not.toHaveFocus();
    close.style.visibility = "visible";
    await waitFor(() => expect(close).toHaveFocus());
    fireEvent.keyDown(document, { key: "Escape" });
    expect(opener).toHaveFocus();

    close.style.visibility = "hidden";
    fireEvent.click(opener);
    fireEvent.keyDown(document, { key: "Escape" });
    close.style.visibility = "visible";
    await new Promise<void>((resolve) =>
      requestAnimationFrame(() => requestAnimationFrame(() => resolve())),
    );
    expect(opener).toHaveFocus();
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });
});
