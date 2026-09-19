import type { ReactNode } from "react";
import type { TriageTier } from "../api/types";
import { DISCLAIMER } from "../api/demo";

export const tierLabels: Record<TriageTier, string> = {
  self_serve: "Self-serve",
  self_serve_with_escalation_path: "Self-serve, with an escalation path",
  legal_aid_recommended: "Legal aid recommended",
  lawyer_now: "Talk to a lawyer now",
};

export function formatDate(value?: string | null, options: Intl.DateTimeFormatOptions = {}): string {
  if (!value) return "No date stated";
  const date = new Date(`${value.length === 10 ? `${value}T12:00:00` : value}`);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat(undefined, { month: "short", day: "numeric", year: "numeric", ...options }).format(date);
}

export function daysUntil(value?: string | null): number | null {
  if (!value) return null;
  const deadline = new Date(`${value}T23:59:59`).getTime();
  if (Number.isNaN(deadline)) return null;
  return Math.ceil((deadline - Date.now()) / 86_400_000);
}

export function cx(...classes: Array<string | false | null | undefined>): string {
  return classes.filter(Boolean).join(" ");
}

export function PageHeader({ eyebrow, title, children }: { eyebrow?: string; title: string; children?: ReactNode }) {
  return (
    <header className="mb-7 max-w-4xl">
      {eyebrow && <p className="eyebrow mb-2">{eyebrow}</p>}
      <h1 className="font-display text-3xl font-semibold tracking-[-0.035em] text-ink sm:text-4xl">{title}</h1>
      {children && <div className="mt-3 max-w-2xl text-[15px] leading-6 text-ink/70">{children}</div>}
    </header>
  );
}

export function Disclaimer({ compact = false }: { compact?: boolean }) {
  return (
    <aside className={cx("disclaimer", compact && "disclaimer-compact")} aria-label="Important information">
      <span aria-hidden="true" className="disclaimer-mark">i</span>
      <p>{DISCLAIMER}</p>
    </aside>
  );
}

export function TriageBadge({ tier }: { tier?: TriageTier | null }) {
  if (!tier) return <span className="badge badge-neutral">Reviewing risk</span>;
  const theme = tier === "lawyer_now" ? "badge-danger" : tier === "legal_aid_recommended" ? "badge-warn" : "badge-safe";
  return <span className={cx("badge", theme)}>{tierLabels[tier]}</span>;
}

export function ConfidenceBadge({ confidence }: { confidence?: "high" | "medium" | "low" | null }) {
  if (!confidence) return null;
  return <span className="text-xs font-medium text-ink/55">{confidence[0].toUpperCase() + confidence.slice(1)} confidence</span>;
}

export function SourceSpans({ spans, className }: { spans?: string[]; className?: string }) {
  if (!spans?.length) return null;
  return (
    <div className={cx("flex flex-wrap gap-1.5", className)} aria-label="Document citations">
      {spans.map((span) => <span className="source-pill" key={span}>{span.replace(/:.+$/, "")}</span>)}
    </div>
  );
}

export function LoadingState({ label = "Loading your document…" }: { label?: string }) {
  return (
    <div className="rounded-2xl border border-ink/10 bg-white px-5 py-12 text-center shadow-card">
      <span className="loading-dot" aria-hidden="true" />
      <p className="mt-4 text-sm font-medium text-ink/70">{label}</p>
    </div>
  );
}

export function ErrorNotice({ message, action }: { message: string; action?: ReactNode }) {
  return (
    <div role="alert" className="rounded-xl border border-red-200 bg-red-50 px-4 py-4 text-sm leading-6 text-red-900">
      <p>{message}</p>
      {action && <div className="mt-3">{action}</div>}
    </div>
  );
}

export function EmptyState({ title, detail, action }: { title: string; detail: string; action?: ReactNode }) {
  return (
    <div className="rounded-2xl border border-dashed border-ink/20 bg-white/60 px-6 py-12 text-center">
      <h2 className="font-display text-xl font-semibold text-ink">{title}</h2>
      <p className="mx-auto mt-2 max-w-md text-sm leading-6 text-ink/65">{detail}</p>
      {action && <div className="mt-5">{action}</div>}
    </div>
  );
}

export function BackLink({ onClick, children = "Back" }: { onClick: () => void; children?: ReactNode }) {
  return (
    <button type="button" onClick={onClick} className="mb-5 inline-flex items-center gap-2 text-sm font-semibold text-pine hover:text-pine/75">
      <span aria-hidden="true">←</span>{children}
    </button>
  );
}

export function Icon({ name, className = "" }: { name: "arrow" | "calendar" | "document" | "scale" | "chat" | "check" | "download" | "warning" | "plus" | "clock" | "link"; className?: string }) {
  const paths: Record<string, ReactNode> = {
    arrow: <path d="M5 12h14M13 6l6 6-6 6" />,
    calendar: <><rect x="3" y="5" width="18" height="16" rx="2" /><path d="M16 3v4M8 3v4M3 10h18" /></>,
    document: <><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" /><path d="M14 2v6h6M8 13h8M8 17h5" /></>,
    scale: <><path d="M12 3v18M5 7h14M7 7l-4 7h8L7 7ZM17 7l-4 7h8l-4-7Z" /></>,
    chat: <><path d="M21 11.5a8.4 8.4 0 0 1-9 8.5 9.8 9.8 0 0 1-4.7-1.2L3 20l1.4-4A8.4 8.4 0 0 1 3 11.5 8.5 8.5 0 0 1 12 3a8.5 8.5 0 0 1 9 8.5Z" /></>,
    check: <path d="m5 12 4 4L19 6" />,
    download: <><path d="M12 3v12M7 10l5 5 5-5M5 21h14" /></>,
    warning: <><path d="M10.3 3.1 1.9 17a2 2 0 0 0 1.7 3h16.8a2 2 0 0 0 1.7-3L13.7 3.1a2 2 0 0 0-3.4 0Z" /><path d="M12 9v4M12 17h.01" /></>,
    plus: <path d="M12 5v14M5 12h14" />,
    clock: <><circle cx="12" cy="12" r="9" /><path d="M12 7v5l3 2" /></>,
    link: <><path d="M10 13a5 5 0 0 0 7.1.1l2-2a5 5 0 0 0-7.1-7.1l-1.1 1.1" /><path d="M14 11a5 5 0 0 0-7.1-.1l-2 2A5 5 0 0 0 12 20l1.1-1.1" /></>,
  };
  return <svg className={cx("icon", className)} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">{paths[name]}</svg>;
}
