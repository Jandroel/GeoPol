import { useEffect, useRef, type ReactNode } from "react";
import {
  AlertCircle,
  ArrowRight,
  CheckCircle2,
  ChevronLeft,
  ChevronRight,
  FileSearch,
  LoaderCircle,
} from "lucide-react";
import { Link } from "react-router-dom";
import { label, number } from "../lib/format";

export function ErrorNotice({ error }: { error: unknown }) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (error) ref.current?.focus();
  }, [error]);
  if (!error) return null;
  return (
    <div className="notice error" role="alert" tabIndex={-1} ref={ref}>
      <AlertCircle size={19} aria-hidden="true" />
      <span>{error instanceof Error ? error.message : String(error)}</span>
    </div>
  );
}
export function Notice({ children }: { children: ReactNode }) {
  return (
    <div className="notice">
      <AlertCircle size={18} aria-hidden="true" />
      <span>{children}</span>
    </div>
  );
}
export function Loading({ text = "Cargando información…" }: { text?: string }) {
  return (
    <div className="loading" role="status">
      <LoaderCircle className="spin" size={22} aria-hidden="true" />
      {text}
    </div>
  );
}
export function Badge({ value }: { value: string }) {
  const kind =
    /ACEPTADO|ACCEPTED|COMPLETED|accepted/.test(value) &&
    value !== "COMPLETED_WITH_ISSUES"
      ? "good"
      : /REVISION|REVIEW|ISSUES|review/.test(value)
        ? "warn"
        : /ERROR|FAILED|SIN_COINCIDENCIA|UNRESOLVED|unresolved/.test(value)
          ? "bad"
          : "neutral";
  return (
    <span className={`badge ${kind}`}>
      <span className="badge-dot" />
      {label(value)}
    </span>
  );
}
export function PageHeader({
  eyebrow,
  title,
  description,
  actions,
}: {
  eyebrow: string;
  title: string;
  description?: string;
  actions?: ReactNode;
}) {
  return (
    <div className="page-heading">
      <div>
        <div className="eyebrow">{eyebrow}</div>
        <h1>{title}</h1>
        {description && <p>{description}</p>}
      </div>
      {actions && <div className="heading-actions">{actions}</div>}
    </div>
  );
}
export function Empty({
  title,
  text,
  action,
}: {
  title: string;
  text: string;
  action?: ReactNode;
}) {
  return (
    <div className="empty">
      <div className="empty-icon">
        <FileSearch size={27} aria-hidden="true" />
      </div>
      <h3>{title}</h3>
      <p>{text}</p>
      {action}
    </div>
  );
}
export function Pagination({
  page,
  total,
  pageSize = 25,
  onChange,
}: {
  page: number;
  total: number;
  pageSize?: number;
  onChange: (page: number) => void;
}) {
  const pages = Math.max(1, Math.ceil(total / pageSize));
  return (
    <div className="pagination">
      <span>
        {number(total)} registros · Página {page} de {pages}
      </span>
      <div>
        <button
          className="button secondary icon"
          onClick={() => onChange(page - 1)}
          disabled={page <= 1}
          aria-label="Página anterior"
        >
          <ChevronLeft size={18} />
        </button>
        <button
          className="button secondary icon"
          onClick={() => onChange(page + 1)}
          disabled={page >= pages}
          aria-label="Página siguiente"
        >
          <ChevronRight size={18} />
        </button>
      </div>
    </div>
  );
}
export function ViewLink({
  to,
  children = "Ver detalle",
}: {
  to: string;
  children?: ReactNode;
}) {
  return (
    <Link className="text-link" to={to}>
      {children}
      <ArrowRight size={16} aria-hidden="true" />
    </Link>
  );
}
export function Success({ children }: { children: ReactNode }) {
  return (
    <div className="notice success" role="status">
      <CheckCircle2 size={18} aria-hidden="true" />
      {children}
    </div>
  );
}
