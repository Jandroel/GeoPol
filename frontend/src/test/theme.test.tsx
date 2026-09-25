import { act, fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ThemeProvider, ThemeToggle, useTheme } from "../theme";

let dark = false;
let listeners: Set<(event: MediaQueryListEvent) => void>;
function systemTheme(value: boolean) {
  dark = value;
  act(() =>
    listeners.forEach((listener) =>
      listener({ matches: value } as MediaQueryListEvent),
    ),
  );
}
function Controls() {
  const { theme, preference, useSystemTheme } = useTheme();
  return (
    <>
      <ThemeToggle />
      <output aria-label="Preferencia de tema">
        {preference ?? "system"}: {theme}
      </output>
      <button onClick={useSystemTheme}>Seguir al sistema</button>
    </>
  );
}
function show() {
  return render(
    <ThemeProvider>
      <Controls />
    </ThemeProvider>,
  );
}

beforeEach(() => {
  localStorage.clear();
  dark = false;
  listeners = new Set();
  vi.stubGlobal(
    "matchMedia",
    vi.fn(() => ({
      get matches() {
        return dark;
      },
      addEventListener: (
        _name: string,
        listener: (event: MediaQueryListEvent) => void,
      ) => listeners.add(listener),
      removeEventListener: (
        _name: string,
        listener: (event: MediaQueryListEvent) => void,
      ) => listeners.delete(listener),
    })),
  );
});
afterEach(() => {
  vi.unstubAllGlobals();
  document.documentElement.removeAttribute("data-theme");
  document.documentElement.style.colorScheme = "";
  document.documentElement.style.backgroundColor = "";
});

describe("Theme preference", () => {
  it("follows the operating system until a choice is saved, and can resume following it", async () => {
    dark = true;
    const user = userEvent.setup();
    show();
    expect(document.documentElement).toHaveAttribute("data-theme", "dark");
    expect(localStorage.getItem("geopol.theme")).toBeNull();
    systemTheme(false);
    expect(document.documentElement).toHaveAttribute("data-theme", "light");
    await user.click(
      screen.getByRole("button", { name: "Activar tema oscuro" }),
    );
    expect(localStorage.getItem("geopol.theme")).toBe("dark");
    systemTheme(true);
    systemTheme(false);
    expect(document.documentElement).toHaveAttribute("data-theme", "dark");
    await user.click(screen.getByRole("button", { name: "Seguir al sistema" }));
    expect(localStorage.getItem("geopol.theme")).toBeNull();
    expect(document.documentElement).toHaveAttribute("data-theme", "light");
  });

  it("restores the explicit selection across provider remounts", async () => {
    localStorage.setItem("geopol.theme", "dark");
    const user = userEvent.setup();
    const view = show();
    expect(
      screen.getByRole("button", { name: "Activar tema claro" }),
    ).toBeVisible();
    await user.click(
      screen.getByRole("button", { name: "Activar tema claro" }),
    );
    view.unmount();
    dark = true;
    show();
    expect(document.documentElement).toHaveAttribute("data-theme", "light");
    expect(document.documentElement.style.colorScheme).toBe("light");
  });

  it("synchronizes a changed or cleared preference from another tab", () => {
    show();
    fireEvent(
      window,
      new StorageEvent("storage", { key: "geopol.theme", newValue: "dark" }),
    );
    expect(document.documentElement).toHaveAttribute("data-theme", "dark");
    fireEvent(
      window,
      new StorageEvent("storage", { key: "geopol.theme", newValue: null }),
    );
    expect(document.documentElement).toHaveAttribute("data-theme", "light");
  });

  it("keeps the toggle usable when browser storage is unavailable", async () => {
    vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
      throw new Error("Storage unavailable");
    });
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new Error("Storage unavailable");
    });
    const user = userEvent.setup();
    show();
    await user.click(
      screen.getByRole("button", { name: "Activar tema oscuro" }),
    );
    expect(document.documentElement).toHaveAttribute("data-theme", "dark");
  });

  it("ignores an unknown stored value and removes the OS listener on unmount", () => {
    localStorage.setItem("geopol.theme", "invalid");
    dark = true;
    const view = show();
    expect(document.documentElement).toHaveAttribute("data-theme", "dark");
    expect(listeners.size).toBe(1);
    view.unmount();
    expect(listeners.size).toBe(0);
  });
});
