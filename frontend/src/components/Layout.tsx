import { useEffect, useRef, useState } from "react";
import { NavLink, Outlet, useLocation } from "react-router-dom";
import {
  BookOpen,
  CircleHelp,
  ClipboardCheck,
  Database,
  Files,
  LayoutDashboard,
  LocateFixed,
  LogOut,
  Menu,
  ShieldCheck,
  X,
} from "lucide-react";
import { useAuth } from "../auth";
import { label } from "../lib/format";

const navigation = [
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
  const location = useLocation();
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
          <span>
            GeoPol<small>INTELIGENCIA TERRITORIAL</small>
          </span>
        </NavLink>
        <button
          className="mobile-close icon"
          onClick={() => setOpen(false)}
          aria-label="Cerrar navegación"
        >
          <X />
        </button>
        <div className="nav-label">ESPACIO DE TRABAJO</div>
        <nav aria-label="Navegación principal">
          {navigation.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.to === "/"}
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
        <div className="sidebar-bottom">
          <div className="sidebar-note">
            <ShieldCheck size={20} aria-hidden="true" />
            <strong>Decisiones verificables</strong>
            <p>Cada resultado conserva su método, evidencia y revisión.</p>
          </div>
          <NavLink
            to="/rules"
            className="help-link"
            onClick={() => setOpen(false)}
          >
            <CircleHelp size={17} aria-hidden="true" />
            Acerca de este MVP<span>0.1</span>
          </NavLink>
        </div>
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
            <span>Espacio de trabajo</span>
            <span className="crumb-divider">/</span>
            <strong>
              {location.pathname === "/"
                ? "Vista general"
                : location.pathname.includes("/results/")
                  ? "Detalle de ubicación"
                  : (navigation.find(
                      (n) => n.to !== "/" && location.pathname.startsWith(n.to),
                    )?.label ?? "Auditoría")}
            </strong>
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
        <footer className="workspace-footer">
          <span>GeoPol · Normalización y geocodificación</span>
          <span>Los resultados expresan evidencia, no certeza absoluta.</span>
        </footer>
      </div>
    </div>
  );
}
