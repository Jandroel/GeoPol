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
import { ThemeProvider } from "../theme";

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
    <ThemeProvider>
      <MemoryRouter initialEntries={[path]}>
        <Routes>
          <Route element={<Layout />}>
            <Route path="*" element={<button>Acción del contenido</button>} />
          </Route>
        </Routes>
      </MemoryRouter>
    </ThemeProvider>,
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
    await user.click(within(nav).getByRole("link", { name: "Estadística" }));
    expect(
      within(nav).getByRole("link", { name: "Estadística" }),
    ).toHaveAttribute("aria-current", "page");
    expect(
      within(
        screen.getByRole("navigation", { name: "Ubicación actual" }),
      ).getByText("Estadística"),
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
      within(nav).getByRole("link", { name: "Procedimientos" }),
    ).toHaveAttribute("aria-current", "page");
    expect(
      within(nav).getByRole("link", { name: "Validación" }),
    ).not.toHaveAttribute("aria-current");
    const breadcrumb = screen.getByRole("navigation", {
      name: "Ubicación actual",
    });
    expect(
      within(breadcrumb).getByText("Detalle del procesamiento"),
    ).toHaveAttribute("aria-current", "page");
    await user.click(
      within(breadcrumb).getByRole("link", { name: "Procedimientos" }),
    );
    expect(
      within(breadcrumb).queryByText("Detalle del procesamiento"),
    ).not.toBeInTheDocument();
  });

  it("mantiene los cinco módulos y omite las acciones locales no autorizadas para un revisor", () => {
    auth.user.role = "reviewer";
    const view = show("/references");
    const nav = screen.getByRole("navigation", {
      name: "Navegación principal",
    });
    expect(within(nav).getAllByRole("link")).toHaveLength(5);
    expect(
      within(
        screen.getByRole("navigation", { name: "Secciones de Validación" }),
      ).queryByRole("link", { name: "Validar archivo" }),
    ).not.toBeInTheDocument();
    expect(
      within(nav).getByRole("link", { name: "Validación" }),
    ).toHaveAttribute("aria-current", "page");
    view.unmount();
    show("/documentation");
    expect(
      within(
        screen.getByRole("navigation", { name: "Secciones de Documentación" }),
      ).queryByRole("link", { name: "Auditoría" }),
    ).not.toBeInTheDocument();
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
    const last = within(drawer).getByRole("link", { name: "Documentación" });
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
        name: "Procedimientos",
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

  it.each([
    ["/runs/new", "Validación"],
    ["/references", "Validación"],
    ["/runs/history?tab=exports", "Procedimientos"],
    ["/review?run_id=history&quality_flag=1", "Procedimientos"],
    ["/results/location?back=%2Freview", "Procedimientos"],
    ["/quality?run_id=history", "Estadística"],
    ["/rules", "Documentación"],
  ])(
    "conserva el módulo correcto al abrir el enlace anterior %s",
    (path, module) => {
      show(path);
      const nav = screen.getByRole("navigation", {
        name: "Navegación principal",
      });
      expect(within(nav).getByRole("link", { name: module })).toHaveAttribute(
        "aria-current",
        "page",
      );
      expect(
        within(nav)
          .getAllByRole("link")
          .filter((link) => link.getAttribute("aria-current") === "page"),
      ).toHaveLength(1);
    },
  );

  it("omite auditoría en la navegación también para administradores", () => {
    show("/documentation");
    const local = screen.getByRole("navigation", {
      name: "Secciones de Documentación",
    });
    expect(
      within(local).queryByRole("link", { name: "Auditoría" }),
    ).not.toBeInTheDocument();
    expect(
      within(
        screen.getByRole("navigation", { name: "Navegación principal" }),
      ).getByRole("link", { name: "Documentación" }),
    ).toHaveAttribute("aria-current", "page");
  });

  it("mantiene el control de tema disponible en la cabecera móvil sin abrir el menú", async () => {
    localStorage.setItem("geopol.theme", "light");
    viewport(true);
    const user = userEvent.setup();
    show("/documentation");
    await user.click(
      screen.getByRole("button", { name: "Activar tema oscuro" }),
    );
    expect(document.documentElement).toHaveAttribute("data-theme", "dark");
    expect(
      screen.getByRole("button", { name: "Activar tema claro" }),
    ).toBeVisible();
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });
});
