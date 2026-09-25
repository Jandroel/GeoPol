import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { Link, Outlet, useLocation } from "react-router-dom";
import {
  BookOpenText,
  ChartNoAxesCombined,
  ChevronRight,
  FileCheck,
  LayoutDashboard,
  MapPinned,
  LogOut,
  Menu,
  PanelLeftClose,
  PanelLeftOpen,
  Workflow,
  X,
} from "lucide-react";
import { useAuth } from "../auth";
import { label } from "../lib/format";
import { ThemeToggle } from "../theme";
import "./navigation.css";

const navigation = [
  { to: "/", label: "Vista general", icon: LayoutDashboard, accent: "sky" },
  {
    to: "/validation",
    label: "Validación",
    icon: FileCheck,
    accent: "teal",
  },
  {
    to: "/procedures",
    label: "Procedimientos",
    icon: Workflow,
    accent: "amber",
  },
  {
    to: "/statistics",
    label: "Estadística",
    icon: ChartNoAxesCombined,
    accent: "violet",
  },
  {
    to: "/documentation",
    label: "Documentación",
    icon: BookOpenText,
    accent: "rose",
  },
];
const sections: Record<
  string,
  { to: string; label: string; manage?: boolean; admin?: boolean }[]
> = {
  "/validation": [
    { to: "/validation", label: "Validar archivo", manage: true },
    { to: "/references", label: "Catálogos de referencia" },
  ],
  "/procedures": [
    { to: "/procedures", label: "Procedimientos" },
    { to: "/runs", label: "Procesamientos" },
    { to: "/review", label: "Revisión de ubicaciones" },
  ],
  "/documentation": [
    { to: "/documentation", label: "Biblioteca" },
    { to: "/rules", label: "Reglas y metodología" },
  ],
};
function modulePath(path: string) {
  if (["/validation", "/runs/new", "/references"].includes(path))
    return "/validation";
  if (
    ["/procedures", "/runs", "/review"].includes(path) ||
    path.startsWith("/runs/") ||
    path.startsWith("/results/")
  )
    return "/procedures";
  if (["/statistics", "/quality"].includes(path)) return "/statistics";
  if (["/documentation", "/rules"].includes(path)) return "/documentation";
  return path;
}
const mobileQuery = "(max-width: 760px)";
const collapseKey = "geopol.navigation.collapsed";
function savedCollapsed() {
  try {
    return localStorage.getItem(collapseKey) === "true";
  } catch {
    return false;
  }
}

export function Layout() {
  const { user, logout } = useAuth();
  const location = useLocation();
  const [open, setOpen] = useState(false);
  const [collapsed, setCollapsed] = useState(savedCollapsed);
  const [mobile, setMobile] = useState(
    () => window.matchMedia?.(mobileQuery).matches ?? false,
  );
  const sidebar = useRef<HTMLElement>(null);
  const menuButton = useRef<HTMLButtonElement>(null);
  const mobileRef = useRef(mobile);
  mobileRef.current = mobile;
  const drawerOpen = mobile && open;
  const compact = !mobile && collapsed;
  const canManage = ["admin", "operator"].includes(user?.role ?? "");
  const runDetail =
    location.pathname.startsWith("/runs/") && location.pathname !== "/runs/new";
  const resultDetail = location.pathname.startsWith("/results/");
  const activePath = modulePath(location.pathname);
  const current = navigation.find((item) => item.to === activePath);
  const localItems = (sections[activePath] ?? []).filter(
    (item) =>
      (!item.admin || user?.role === "admin") && (!item.manage || canManage),
  );
  const localPath = runDetail
    ? "/runs"
    : resultDetail
      ? "/review"
      : location.pathname === "/runs/new"
        ? "/validation"
        : location.pathname;

  useEffect(() => {
    const query = window.matchMedia?.(mobileQuery);
    if (!query) return;
    const resize = (event: MediaQueryListEvent) => {
      mobileRef.current = event.matches;
      setMobile(event.matches);
      if (!event.matches) setOpen(false);
    };
    query.addEventListener("change", resize);
    return () => query.removeEventListener("change", resize);
  }, []);

  useEffect(() => {
    setOpen(false);
  }, [location.pathname, location.search]);
  useEffect(() => {
    try {
      localStorage.setItem(collapseKey, String(collapsed));
    } catch {
      /* Navigation remains usable when browser storage is unavailable. */
    }
  }, [collapsed]);

  useLayoutEffect(() => {
    if (!drawerOpen) return;
    let focusFrame = 0;
    let cancelled = false;
    const focusWhenAvailable = () => {
      const drawer = sidebar.current;
      if (cancelled || !drawer) return;
      // Do not interrupt a user who has already moved into the navigation.
      if (drawer.contains(document.activeElement)) return;
      const button = drawer.querySelector<HTMLButtonElement>(".mobile-close");
      if (
        button &&
        !button.closest("[inert]") &&
        getComputedStyle(button).visibility === "visible"
      ) {
        button.focus();
        if (document.activeElement === button) return;
      }
      // A breakpoint/style update may still expose the closed drawer's
      // visibility during the commit. Wait for focusability, not N frames.
      focusFrame = requestAnimationFrame(focusWhenAvailable);
    };
    focusWhenAvailable();
    return () => {
      cancelled = true;
      cancelAnimationFrame(focusFrame);
    };
  }, [drawerOpen]);

  useEffect(() => {
    if (!drawerOpen) return;
    const originalOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    const controls = () =>
      Array.from(
        sidebar.current?.querySelectorAll<HTMLElement>(
          'a[href], button:not([disabled]), [tabindex="0"]',
        ) ?? [],
      );
    const keyboard = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        event.preventDefault();
        setOpen(false);
      }
      if (event.key !== "Tab") return;
      const elements = controls();
      const first = elements[0],
        last = elements.at(-1);
      if (
        event.shiftKey &&
        (document.activeElement === first ||
          !sidebar.current?.contains(document.activeElement))
      ) {
        event.preventDefault();
        last?.focus();
      } else if (
        !event.shiftKey &&
        (document.activeElement === last ||
          !sidebar.current?.contains(document.activeElement))
      ) {
        event.preventDefault();
        first?.focus();
      }
    };
    document.addEventListener("keydown", keyboard);
    return () => {
      document.removeEventListener("keydown", keyboard);
      document.body.style.overflow = originalOverflow;
      if (mobileRef.current) menuButton.current?.focus();
    };
  }, [drawerOpen]);

  return (
    <div
      className={`app-shell navigation-shell ${compact ? "navigation-compact" : ""}`}
    >
      <a className="skip-link" href="#main-content" inert={drawerOpen}>
        Ir al contenido principal
      </a>
      {drawerOpen && (
        <button
          className="sidebar-scrim navigation-scrim"
          aria-label="Cerrar navegación"
          tabIndex={-1}
          onClick={() => setOpen(false)}
        />
      )}
      <aside
        ref={sidebar}
        id="workspace-navigation"
        className={`sidebar ${drawerOpen ? "open" : ""}`}
        inert={mobile && !open}
        role={drawerOpen ? "dialog" : undefined}
        aria-modal={drawerOpen ? true : undefined}
        aria-label={drawerOpen ? "Menú de navegación" : undefined}
      >
        <div className="navigation-brand-row">
          <Link
            className="brand"
            to="/"
            aria-label="GeoPol, vista general"
            title={compact ? "GeoPol, vista general" : undefined}
            onClick={() => setOpen(false)}
          >
            <span className="brand-mark">
              <MapPinned strokeWidth={1.6} aria-hidden="true" />
            </span>
            <span className="navigation-brand-copy">
              <strong>GeoPol</strong>
              <span className="navigation-brand-subtitle">
                INEI · Información geoespacial
              </span>
            </span>
          </Link>
          {mobile && (
            <button
              className="mobile-close icon"
              onClick={() => setOpen(false)}
              aria-label="Cerrar navegación"
            >
              <X aria-hidden="true" size={20} />
            </button>
          )}
          {!mobile && (
            <button
              className="navigation-collapse"
              onClick={() => setCollapsed((value) => !value)}
              aria-label={compact ? "Expandir menú" : "Contraer menú"}
              aria-expanded={!compact}
              aria-controls="workspace-navigation"
              title={compact ? "Expandir menú" : "Contraer menú"}
            >
              {compact ? (
                <PanelLeftOpen size={19} aria-hidden="true" />
              ) : (
                <PanelLeftClose size={19} aria-hidden="true" />
              )}
            </button>
          )}
        </div>
        <nav aria-label="Navegación principal">
          <div className="navigation-group">
            {navigation.map((item) => (
              <Link
                key={item.to}
                to={item.to}
                onClick={() => setOpen(false)}
                aria-label={item.label}
                aria-current={item.to === activePath ? "page" : undefined}
                title={compact ? item.label : undefined}
                className={`nav-item ${item.to === activePath ? "active" : ""}`}
                data-accent={item.accent}
              >
                <span className="navigation-module-icon" aria-hidden="true">
                  <item.icon size={24} strokeWidth={2} />
                </span>
                <span className="navigation-link-label">{item.label}</span>
                <ChevronRight
                  className="navigation-active-arrow"
                  size={15}
                  aria-hidden="true"
                />
              </Link>
            ))}
          </div>
        </nav>
      </aside>
      <div className="workspace" inert={drawerOpen}>
        <header className="topbar">
          <div className="navigation-context">
            {mobile && (
              <button
                ref={menuButton}
                className="mobile-menu icon"
                onClick={() => setOpen(true)}
                aria-label="Abrir navegación"
                aria-controls="workspace-navigation"
                aria-expanded={drawerOpen}
              >
                <Menu size={22} aria-hidden="true" />
              </button>
            )}
          </div>
          <div className="account">
            <ThemeToggle />
            <div className="avatar" aria-hidden="true">
              {user?.username.slice(0, 2).toUpperCase()}
            </div>
            <div className="navigation-account-copy">
              <strong>{user?.username}</strong>
              <small>{label(user?.role)}</small>
            </div>
            <button
              className="icon logout"
              aria-label="Cerrar sesión"
              title="Cerrar sesión"
              onClick={() => void logout().catch(() => undefined)}
            >
              <LogOut size={18} aria-hidden="true" />
            </button>
          </div>
        </header>
        <main id="main-content" className="main-content" tabIndex={-1}>
          {current && localItems.length > 0 && (
            <nav
              className="module-sections"
              aria-label={`Secciones de ${current.label}`}
            >
              {localItems.map((item) => (
                <Link
                  key={item.to}
                  to={item.to}
                  aria-current={item.to === localPath ? "page" : undefined}
                >
                  {item.label}
                </Link>
              ))}
            </nav>
          )}
          <Outlet />
        </main>
      </div>
    </div>
  );
}
