import type { ReactNode } from "react";
import { navigate, useHashRoute, useWayfinder } from "../app";
import { DEMO_DOCUMENT_ID } from "../api/demo";
import { Icon, cx } from "./ui";

interface NavItem {
  label: string;
  icon: "document" | "scale" | "calendar" | "chat";
  path: string;
  active: (route: string) => boolean;
}

export function AppShell({ children }: { children: ReactNode }) {
  const route = useHashRoute();
  const { activeDocument, useDemo } = useWayfinder();
  const documentId = activeDocument?.document_id;
  const hasDocument = Boolean(documentId);
  const navItems: NavItem[] = [
    {
      label: "Your decisions",
      icon: "scale",
      path: documentId ? `/documents/${documentId}/decisions` : "/upload",
      active: (value) => value.includes("/decisions") || value.startsWith("/decisions/"),
    },
    {
      label: "Clauses",
      icon: "document",
      path: documentId ? `/documents/${documentId}/clauses` : "/upload",
      active: (value) => value.includes("/clauses"),
    },
    {
      label: "Deadlines",
      icon: "calendar",
      path: "/tracker",
      active: (value) => value === "/tracker",
    },
    {
      label: "Compare",
      icon: "scale",
      path: "/compare",
      active: (value) => value === "/compare",
    },
  ];

  const documentLabel = activeDocument?.original_filename || (documentId === DEMO_DOCUMENT_ID ? "Demo notice" : "No document selected");

  return (
    <div className="min-h-screen bg-paper text-ink">
      <a href="#main-content" className="skip-link">Skip to content</a>
      <header className="sticky top-0 z-20 border-b border-ink/10 bg-paper/90 backdrop-blur">
        <div className="mx-auto flex h-16 max-w-7xl items-center justify-between px-4 sm:px-6 lg:px-8">
          <button type="button" onClick={() => navigate(hasDocument ? `/documents/${documentId}/decisions` : "/upload")} className="flex items-center gap-3 text-left">
            <span className="brand-mark" aria-hidden="true"><span /></span>
            <span><span className="font-display text-xl font-semibold tracking-[-0.04em]">Wayfinder</span><span className="ml-2 hidden text-xs text-ink/55 sm:inline">Know your move</span></span>
          </button>
          <div className="flex items-center gap-2">
            <span className="hidden max-w-52 truncate rounded-full bg-ink/5 px-3 py-1.5 text-xs font-medium text-ink/65 md:block">{documentLabel}</span>
            <button type="button" className="button button-secondary button-small" onClick={() => { useDemo(); navigate(`/documents/${DEMO_DOCUMENT_ID}/decisions`); }}>
              View demo
            </button>
            <button type="button" className="button button-primary button-small" onClick={() => navigate("/upload")}>Add document</button>
          </div>
        </div>
      </header>
      <div className="mx-auto flex max-w-7xl">
        <aside className="hidden w-60 shrink-0 border-r border-ink/10 px-4 py-7 lg:block" aria-label="Main navigation">
          <nav className="space-y-1">
            {navItems.map((item) => (
              <button key={item.label} type="button" onClick={() => navigate(item.path)} className={cx("nav-item w-full", item.active(route) && "nav-item-active")}>
                <Icon name={item.icon} className="h-4 w-4" /> {item.label}
              </button>
            ))}
          </nav>
          <div className="mt-9 rounded-xl bg-sage/45 p-4">
            <p className="text-xs font-semibold uppercase tracking-[0.12em] text-pine">Decision-first</p>
            <p className="mt-2 text-xs leading-5 text-ink/65">Start with what needs a response, then inspect the document evidence.</p>
          </div>
        </aside>
        <main id="main-content" className="min-w-0 flex-1 px-4 py-8 pb-24 sm:px-6 lg:px-10 lg:py-10">{children}</main>
      </div>
      <nav className="fixed inset-x-0 bottom-0 z-20 flex border-t border-ink/10 bg-paper px-2 py-2 shadow-[0_-4px_16px_rgba(23,33,25,0.06)] lg:hidden" aria-label="Main navigation">
        {navItems.map((item) => <button key={item.label} type="button" onClick={() => navigate(item.path)} className={cx("mobile-nav-item", item.active(route) && "mobile-nav-item-active")}><Icon name={item.icon} className="h-[18px] w-[18px]" /><span>{item.label}</span></button>)}
      </nav>
    </div>
  );
}
