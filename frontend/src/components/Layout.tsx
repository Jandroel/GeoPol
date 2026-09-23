import { useEffect, useRef, useState } from "react";
import { Link, Outlet, useLocation } from "react-router-dom";
import {
  BookOpen,
  ChartNoAxesCombined,
  ChevronRight,
  ClipboardCheck,
  Database,
  Files,
  FileUp,
  LayoutDashboard,
  LocateFixed,
  LogOut,
  Menu,
  PanelLeftClose,
  PanelLeftOpen,
  ShieldCheck,
  X,
} from "lucide-react";
import { useAuth } from "../auth";
import { label } from "../lib/format";
import "./navigation.css";

const navigation = [
  {
    to: "/runs/new",
    label: "Carga de archivos",
    icon: FileUp,
    group: "Trabajo",
  },
  {
    to: "/quality",
    label: "Seguimiento por calidad",
    icon: ChartNoAxesCombined,
    group: "Trabajo",
  },
  { to: "/", label: "Vista general", icon: LayoutDashboard, group: "Trabajo" },
  { to: "/runs", label: "Procesamientos", icon: Files, group: "Trabajo" },
  {
    to: "/review",
    label: "Revisión de ubicaciones",
    icon: ClipboardCheck,
    group: "Trabajo",
  },
  {
    to: "/references",
    label: "Catálogos de referencia",
    icon: Database,
    group: "Referencias",
  },
  {
    to: "/rules",
    label: "Reglas y metodología",
    icon: BookOpen,
    group: "Referencias",
  },
  { to: "/audit", label: "Auditoría", icon: ShieldCheck, group: "Control" },
];
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
  const items = navigation.filter((item) =>
    item.to === "/audit"
      ? user?.role === "admin"
      : item.to !== "/runs/new" ||
        ["admin", "operator"].includes(user?.role ?? ""),
  );
  const runDetail =
    location.pathname.startsWith("/runs/") && location.pathname !== "/runs/new";
  const resultDetail = location.pathname.startsWith("/results/");
  const activePath = runDetail
    ? "/runs"
    : resultDetail
      ? "/review"
      : location.pathname;
  const current = items.find((item) => item.to === activePath);
  const detailTitle = runDetail
    ? "Detalle del procesamiento"
    : resultDetail
      ? "Detalle de ubicación"
      : null;

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

  useEffect(() => {
    if (!drawerOpen) return;
    const originalOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    let focusFrame = requestAnimationFrame(() => {
      // The browser must render the newly visible, non-inert drawer before
      // accepting focus. One frame can still precede that style update.
      focusFrame = requestAnimationFrame(() => {
        sidebar.current
          ?.querySelector<HTMLButtonElement>(".mobile-close")
          ?.focus({ preventScroll: true });
      });
    });
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
      cancelAnimationFrame(focusFrame);
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
              <LocateFixed aria-hidden="true" />
            </span>
            <span className="navigation-brand-copy">GeoPol</span>
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
        </div>
        <nav aria-label="Navegación principal">
          {["Trabajo", "Referencias", "Control"].map((group) => {
            const groupItems = items.filter((item) => item.group === group);
            return groupItems.length ? (
              <div className="navigation-group" key={group}>
                <p className="navigation-group-title">{group}</p>
                {groupItems.map((item) => (
                  <Link
                    key={item.to}
                    to={item.to}
                    onClick={() => setOpen(false)}
                    aria-label={item.label}
                    aria-current={item.to === activePath ? "page" : undefined}
                    title={compact ? item.label : undefined}
                    className={`nav-item ${item.to === activePath ? "active" : ""}`}
                  >
                    <item.icon size={20} aria-hidden="true" />
                    <span className="navigation-link-label">{item.label}</span>
                    <ChevronRight
                      className="navigation-active-arrow"
                      size={15}
                      aria-hidden="true"
                    />
                  </Link>
                ))}
              </div>
            ) : null;
          })}
        </nav>
        {!mobile && (
          <div className="navigation-footer">
            <button
              className="navigation-collapse"
              onClick={() => setCollapsed((value) => !value)}
              aria-label={compact ? "Expandir menú" : "Contraer menú"}
              aria-expanded={!compact}
              aria-controls="workspace-navigation"
              title={compact ? "Expandir menú" : undefined}
            >
              {compact ? (
                <PanelLeftOpen size={20} aria-hidden="true" />
              ) : (
                <PanelLeftClose size={20} aria-hidden="true" />
              )}
              <span>Contraer menú</span>
            </button>
          </div>
        )}
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
            <nav
              className="navigation-breadcrumb"
              aria-label="Ubicación actual"
            >
              <Link className="navigation-home" to="/">
                GeoPol
              </Link>
              <ChevronRight
                className="navigation-home-divider"
                size={14}
                aria-hidden="true"
              />
              {detailTitle && current ? (
                <>
                  <Link to={current.to} className="navigation-parent">
                    {current.label}
                  </Link>
                  <ChevronRight
                    className="navigation-parent-divider"
                    size={14}
                    aria-hidden="true"
                  />
                </>
              ) : null}
              <span aria-current="page">
                {detailTitle ?? current?.label ?? "Página no encontrada"}
              </span>
            </nav>
          </div>
          <div className="account">
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
          <Outlet />
        </main>
      </div>
    </div>
  );
}
