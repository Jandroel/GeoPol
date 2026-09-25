import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useLayoutEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import { Moon, Sun } from "lucide-react";

export type Theme = "light" | "dark";
const themeKey = "geopol.theme";
const systemQuery = "(prefers-color-scheme: dark)";
const parsePreference = (value: string | null): Theme | null =>
  value === "light" || value === "dark" ? value : null;
function savedPreference() {
  try {
    return parsePreference(localStorage.getItem(themeKey));
  } catch {
    return null;
  }
}
function systemIsDark() {
  return window.matchMedia?.(systemQuery).matches ?? false;
}
interface ThemeContextValue {
  theme: Theme;
  preference: Theme | null;
  setTheme: (theme: Theme) => void;
  useSystemTheme: () => void;
}
const ThemeContext = createContext<ThemeContextValue | null>(null);

export function ThemeProvider({ children }: { children: ReactNode }) {
  const [preference, setPreference] = useState(savedPreference);
  const [systemDark, setSystemDark] = useState(systemIsDark);
  const theme = preference ?? (systemDark ? "dark" : "light");
  useLayoutEffect(() => {
    document.documentElement.dataset.theme = theme;
    document.documentElement.style.colorScheme = theme;
    document.documentElement.style.backgroundColor =
      theme === "dark" ? "#0c1927" : "#f4f7fa";
    document
      .querySelector('meta[name="theme-color"]')
      ?.setAttribute("content", theme === "dark" ? "#0c1927" : "#f4f7fa");
  }, [theme]);
  useEffect(() => {
    const query = window.matchMedia?.(systemQuery);
    if (!query) return;
    setSystemDark(query.matches);
    const change = (event: MediaQueryListEvent) => setSystemDark(event.matches);
    query.addEventListener("change", change);
    return () => query.removeEventListener("change", change);
  }, []);
  useEffect(() => {
    const sync = (event: StorageEvent) => {
      if (event.key === themeKey || event.key === null)
        setPreference(parsePreference(event.newValue));
    };
    window.addEventListener("storage", sync);
    return () => window.removeEventListener("storage", sync);
  }, []);
  const setTheme = useCallback((next: Theme) => {
    setPreference(next);
    try {
      localStorage.setItem(themeKey, next);
    } catch {
      /* The session still keeps the selected theme when storage is unavailable. */
    }
  }, []);
  const useSystemTheme = useCallback(() => {
    setPreference(null);
    try {
      localStorage.removeItem(themeKey);
    } catch {
      /* System preference is still applied for this session. */
    }
  }, []);
  const value = useMemo(
    () => ({ theme, preference, setTheme, useSystemTheme }),
    [theme, preference, setTheme, useSystemTheme],
  );
  return (
    <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>
  );
}

export function useTheme() {
  const context = useContext(ThemeContext);
  if (!context)
    throw new Error("useTheme debe utilizarse dentro de ThemeProvider");
  return context;
}

export function ThemeToggle({ className = "" }: { className?: string }) {
  const { theme, setTheme } = useTheme();
  const action =
    theme === "dark" ? "Activar tema claro" : "Activar tema oscuro";
  const Icon = theme === "dark" ? Sun : Moon;
  return (
    <button
      type="button"
      className={`theme-toggle ${className}`}
      aria-label={action}
      title={`${theme === "dark" ? "Tema oscuro" : "Tema claro"} · ${action}`}
      onClick={() => setTheme(theme === "dark" ? "light" : "dark")}
    >
      <Icon size={19} aria-hidden="true" />
    </button>
  );
}
