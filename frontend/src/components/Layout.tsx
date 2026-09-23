import { useEffect, useRef, useState } from "react";
import { NavLink, Outlet } from "react-router-dom";
import {
  BookOpen,
  ClipboardCheck,
  Database,
  Files,
  LayoutDashboard,
  LocateFixed,
  LogOut,
  Menu,
  ShieldCheck,
  X,
  FileUp,
  ChartNoAxesCombined,
} from "lucide-react";
import { useAuth } from "../auth";
import { label } from "../lib/format";

const navigation = [
  { to: "/runs/new", label: "Carga de archivos", icon: FileUp },
  {
    to: "/quality",
    label: "Seguimiento por calidad",
    icon: ChartNoAxesCombined,
  },
  { to: "/", label: "Vista general", icon: LayoutDashboard },
  { to: "/runs", label: "Procesamientos", icon: Files },
  { to: "/review", label: "Revisión de ubicaciones", icon: ClipboardCheck },
  { to: "/references", label: "Catálogos de referencia", icon: Database },
  { to: "/rules", label: "Reglas y metodología", icon: BookOpen },
];
export function Layout() {
  const { user, logout } = useAuth();
  const [open, setOpen] = useState(false);
  const sidebar = useRef<HTMLElement>(null);
  const menuButton = useRef<HTMLButtonElement>(null);
  useEffect(() => {
    if (!open) return;
    let focusFrame = requestAnimationFrame(() => {
      // Let visibility and the drawer transform reach the next rendered frame.
      focusFrame = requestAnimationFrame(() => {
        sidebar.current?.querySelector<HTMLAnchorElement>("nav a")?.focus();
      });
    });
    const keyboard = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        event.preventDefault();
        setOpen(false);
      }
      if (event.key !== "Tab") return;
      const controls = Array.from(
        sidebar.current?.querySelectorAll<HTMLElement>("a, button") ?? [],
      ).filter((element) => element.getClientRects().length > 0);
      const first = controls[0],
        last = controls.at(-1);
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last?.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first?.focus();
      }
    };
    document.addEventListener("keydown", keyboard);
    return () => {
      cancelAnimationFrame(focusFrame);
      document.removeEventListener("keydown", keyboard);
      menuButton.current?.focus();
    };
  }, [open]);
  return (
    <div className="app-shell">
      <a className="skip-link" href="#main-content">
        Ir al contenido principal
      </a>
      {open && (
        <button
          className="sidebar-scrim"
          aria-label="Cerrar navegación"
          onClick={() => setOpen(false)}
        />
      )}
      <aside
        ref={sidebar}
        id="workspace-navigation"
        className={`sidebar ${open ? "open" : ""}`}
      >
        <NavLink className="brand" to="/" onClick={() => setOpen(false)}>
          <span className="brand-mark">
            <LocateFixed aria-hidden="true" />
          </span>
          <span>GeoPol</span>
        </NavLink>
        <button
          className="mobile-close icon"
          onClick={() => setOpen(false)}
          aria-label="Cerrar navegación"
        >
          <X />
        </button>
        <nav aria-label="Navegación principal">
          {navigation
            .filter(
              (item) =>
                item.to !== "/runs/new" ||
                ["admin", "operator"].includes(user?.role ?? ""),
            )
            .map((item) => (
              <NavLink
                key={item.to}
                to={item.to}
                end={item.to === "/" || item.to === "/runs"}
                onClick={() => setOpen(false)}
                className={({ isActive }) =>
                  `nav-item ${isActive ? "active" : ""}`
                }
              >
                <item.icon size={19} aria-hidden="true" />
                {item.label}
              </NavLink>
            ))}
          {user?.role === "admin" && (
            <NavLink
              to="/audit"
              onClick={() => setOpen(false)}
              className={({ isActive }) =>
                `nav-item ${isActive ? "active" : ""}`
              }
            >
              <ShieldCheck size={19} aria-hidden="true" />
              Auditoría
            </NavLink>
          )}
        </nav>
      </aside>
      <div className="workspace">
        <header className="topbar">
          <div className="breadcrumb">
            <button
              ref={menuButton}
              className="mobile-menu icon"
              onClick={() => setOpen(true)}
              aria-label="Abrir navegación"
              aria-controls="workspace-navigation"
              aria-expanded={open}
            >
              <Menu size={22} />
            </button>
          </div>
          <div className="account">
            <div className="avatar">
              {user?.username.slice(0, 2).toUpperCase()}
            </div>
            <div>
              <strong>{user?.username}</strong>
              <small>{label(user?.role)}</small>
            </div>
            <button
              className="icon logout"
              aria-label="Cerrar sesión"
              title="Cerrar sesión"
              onClick={() => void logout().catch(() => undefined)}
            >
              <LogOut size={18} />
            </button>
          </div>
        </header>
        <main id="main-content" className="main-content">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
