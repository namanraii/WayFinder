import { useEffect, useState } from "react";
import { api } from "../api/client";
import { demoPrepPack } from "../api/demo";
import type { PrepPack } from "../api/types";
import { navigate } from "../app";
import { BackLink, Disclaimer, ErrorNotice, Icon, LoadingState } from "../components/ui";

export function PrepPackViewScreen({ decisionId }: { decisionId: string }) {
  const [pack, setPack] = useState<PrepPack | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    let cancelled = false;

    async function loadPack() {
      setIsLoading(true);
      setError(null);

      try {
        const data = await api.getPrepPack(decisionId);
        if (!cancelled) setPack(data);
      } catch (err: unknown) {
        if (decisionId.includes("demo")) {
          if (!cancelled) setPack(demoPrepPack);
        } else {
          if (!cancelled) {
            setError(err instanceof Error ? err.message : "Failed to load Prep Pack.");
          }
        }
      } finally {
        if (!cancelled) setIsLoading(false);
      }
    }

    loadPack();
    return () => {
      cancelled = true;
    };
  }, [decisionId]);

  const handlePrint = () => {
    window.print();
  };

  const handleCopy = async () => {
    if (!pack) return;
    const lines = [
      "WAYFINDER — LEGAL CONSULTATION PREP PACK",
      "=========================================",
      "",
      `Summary: ${pack.contents.document_summary || "N/A"}`,
      `Urgency: ${pack.contents.urgency_note || "N/A"}`,
      "",
      "Timeline:",
      ...(pack.contents.timeline?.map((t) => ` - ${t.date}: ${t.event}`) || [" - None stated"]),
      "",
      "Questions for Legal Professional:",
      ...(pack.contents.questions_for_professional?.map((q, i) => ` ${i + 1}. ${q}`) || []),
      "",
      "Note: Wayfinder provides legal information, not legal advice.",
    ];
    try {
      await navigator.clipboard.writeText(lines.join("\n"));
      setCopied(true);
      setTimeout(() => setCopied(false), 2500);
    } catch {
      // Fallback
    }
  };

  if (isLoading) {
    return <LoadingState label="Preparing your consultation Prep Pack…" />;
  }

  if (error || !pack) {
    return (
      <div className="mx-auto max-w-3xl space-y-4">
        <BackLink onClick={() => navigate(`/decisions/${decisionId}`)}>Back</BackLink>
        <ErrorNotice message={error || "Prep Pack not found"} />
      </div>
    );
  }

  const c = pack.contents;

  return (
    <div className="mx-auto max-w-4xl space-y-8 print:p-0">
      <div className="print:hidden">
        <BackLink onClick={() => navigate(`/decisions/${decisionId}`)}>
          Back to decision
        </BackLink>
      </div>

      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between border-b border-ink/10 pb-6">
        <div>
          <p className="eyebrow mb-1">Consultation Prep Pack</p>
          <h1 className="font-display text-3xl font-bold tracking-tight text-ink">
            Everything for your legal consultation
          </h1>
          <p className="mt-1 text-sm text-ink/65">
            Take this summary to a legal aid clinic, tenant union, or attorney.
          </p>
        </div>

        <div className="flex gap-2 print:hidden">
          <button
            type="button"
            onClick={handleCopy}
            className="button button-secondary button-small gap-1.5"
          >
            <Icon name="document" className="h-3.5 w-3.5" />
            {copied ? "Copied!" : "Copy summary"}
          </button>
          <button
            type="button"
            onClick={handlePrint}
            className="button button-primary button-small gap-1.5"
          >
            <Icon name="download" className="h-3.5 w-3.5" />
            Print / PDF
          </button>
        </div>
      </div>

      {/* Urgency Note */}
      {c.urgency_note && (
        <div className="rounded-xl border border-red-200 bg-red-50 p-4 text-xs font-medium leading-5 text-red-900">
          <strong>Urgency:</strong> {c.urgency_note}
        </div>
      )}

      {/* Document Summary */}
      <div className="rounded-2xl border border-ink/10 bg-white p-6 shadow-sm space-y-2">
        <h2 className="text-xs font-bold uppercase tracking-wider text-ink/60">
          Document Summary
        </h2>
        <p className="text-sm leading-6 text-ink/80">{c.document_summary}</p>
      </div>

      {/* Timeline */}
      {c.timeline && c.timeline.length > 0 && (
        <div className="rounded-2xl border border-ink/10 bg-white p-6 shadow-sm space-y-3">
          <h2 className="text-xs font-bold uppercase tracking-wider text-ink/60">
            Document Timeline
          </h2>
          <div className="space-y-2">
            {c.timeline.map((item, idx) => (
              <div key={idx} className="flex items-start gap-4 text-xs">
                <span className="font-mono font-semibold text-pine shrink-0 min-w-24">
                  {item.date || "Date not stated"}
                </span>
                <span className="text-ink/80">{item.event}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Key Questions for the Professional */}
      {c.questions_for_professional && c.questions_for_professional.length > 0 && (
        <div className="rounded-2xl border border-ink/10 bg-white p-6 shadow-sm space-y-3">
          <h2 className="text-xs font-bold uppercase tracking-wider text-pine">
            Recommended Questions to Ask Your Counsel
          </h2>
          <ol className="list-decimal list-inside space-y-2 text-xs leading-6 text-ink/80">
            {c.questions_for_professional.map((q, idx) => (
              <li key={idx} className="pl-1 font-medium text-ink">
                {q}
              </li>
            ))}
          </ol>
        </div>
      )}

      {/* Relevant Clauses */}
      {c.relevant_clause_excerpts && c.relevant_clause_excerpts.length > 0 && (
        <div className="rounded-2xl border border-ink/10 bg-paper p-6 space-y-2">
          <h2 className="text-xs font-bold uppercase tracking-wider text-ink/60">
            Referenced Clause IDs
          </h2>
          <div className="flex flex-wrap gap-1.5">
            {c.relevant_clause_excerpts.map((id) => (
              <span key={id} className="source-pill">
                {id}
              </span>
            ))}
          </div>
        </div>
      )}

      <Disclaimer />
    </div>
  );
}
