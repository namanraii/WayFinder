import { useEffect, useState } from "react";
import { api } from "../api/client";
import { demoDecisions } from "../api/demo";
import type { DecisionPoint } from "../api/types";
import { navigate } from "../app";
import {
  BackLink,
  ConfidenceBadge,
  Disclaimer,
  ErrorNotice,
  Icon,
  LoadingState,
  PageHeader,
  SourceSpans,
  TriageBadge,
  daysUntil,
  formatDate,
} from "../components/ui";

export function DecisionDetailScreen({ decisionId }: { decisionId: string }) {
  const [decision, setDecision] = useState<DecisionPoint | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    async function loadDecision() {
      setIsLoading(true);
      setError(null);

      try {
        const data = await api.getDecision(decisionId);
        if (!cancelled) setDecision(data);
      } catch (err: unknown) {
        // Fallback to demo decision if demo ID
        const match = demoDecisions.find((d) => d.decision_id === decisionId);
        if (match) {
          if (!cancelled) setDecision(match);
        } else {
          if (!cancelled) {
            setError(err instanceof Error ? err.message : "Decision could not be loaded.");
          }
        }
      } finally {
        if (!cancelled) setIsLoading(false);
      }
    }

    loadDecision();
    return () => {
      cancelled = true;
    };
  }, [decisionId]);

  if (isLoading) {
    return <LoadingState label="Loading decision details and options…" />;
  }

  if (error || !decision) {
    return (
      <div className="mx-auto max-w-3xl space-y-4">
        <ErrorNotice message={error || "Decision not found"} />
        <button
          type="button"
          onClick={() => navigate("/upload")}
          className="button button-secondary button-small"
        >
          Return to upload
        </button>
      </div>
    );
  }

  const daysRemaining = decision.days_remaining ?? daysUntil(decision.deadline);
  const isUrgent = daysRemaining !== null && daysRemaining <= 7;
  const isOverdue = daysRemaining !== null && daysRemaining < 0;

  const isEscalatedTier =
    decision.triage_tier === "lawyer_now" || decision.triage_tier === "legal_aid_recommended";

  const inactionOption = decision.options.find((opt) => opt.is_default_if_inaction);
  const activeOptions = decision.options.filter((opt) => !opt.is_default_if_inaction);

  return (
    <div className="mx-auto max-w-4xl space-y-8">
      <BackLink onClick={() => navigate(`/documents/${decision.document_id}/decisions`)}>
        Back to Decision Record
      </BackLink>

      {/* Header */}
      <div>
        <div className="flex flex-wrap items-center gap-2 mb-3">
          <TriageBadge tier={decision.triage_tier} />
          <ConfidenceBadge confidence={decision.confidence} />
          {decision.deadline && (
            <span
              className={`badge ${
                isUrgent ? "badge-danger" : "badge-neutral"
              }`}
            >
              {isOverdue ? "Overdue" : isUrgent ? "Due Soon" : "Deadline"} ·{" "}
              {formatDate(decision.deadline)}
              {daysRemaining !== null &&
                ` (${isOverdue ? `${Math.abs(daysRemaining)}d ago` : `${daysRemaining}d remaining`})`}
            </span>
          )}
        </div>

        <h1 className="font-display text-3xl font-bold tracking-tight text-ink sm:text-4xl">
          {decision.title}
        </h1>
      </div>

      {/* COST OF INACTION — The Core Guarantee */}
      {inactionOption && (
        <div className="rounded-2xl border-2 border-red-200 bg-red-50/70 p-6 sm:p-7 shadow-card">
          <div className="flex items-center gap-2 text-xs font-bold uppercase tracking-wider text-red-900">
            <Icon name="warning" className="h-4 w-4 text-red-700" />
            Cost of Inaction — What happens if you do nothing
          </div>
          <p className="mt-3 font-display text-lg font-semibold leading-7 text-red-950">
            {inactionOption.consequence}
          </p>
          <div className="mt-4 flex flex-wrap items-center justify-between gap-3 pt-2 border-t border-red-200/60 text-xs text-red-900/80">
            <span>
              <strong>Effort:</strong> None · <strong>Stakes:</strong> {inactionOption.cost}
            </span>
            <SourceSpans spans={inactionOption.source_spans || decision.source_spans} />
          </div>
        </div>
      )}

      {/* Triage Reasoning & Tier Gate Note */}
      <div className="rounded-2xl border border-ink/10 bg-white p-6 space-y-4">
        <h2 className="text-xs font-bold uppercase tracking-wider text-ink/60">Triage Assessment</h2>
        
        {decision.triage_reasoning && (
          <p className="text-sm leading-6 text-ink/80">{decision.triage_reasoning}</p>
        )}

        {isEscalatedTier ? (
          <div className="rounded-xl border border-amber-300 bg-amber-50 p-4 text-xs leading-5 text-amber-900 space-y-2">
            <p className="font-semibold">
              Automated self-serve resolution is blocked for this decision.
            </p>
            <p>
              Because this decision carries high stakes or irreversible consequences, Wayfinder does not generate
              a draft letter for you to send alone. Instead, use the <strong>Prep Pack</strong> to walk into a legal aid clinic
              or consultation with your timeline, clauses, and key questions already organized.
            </p>
            <div className="pt-2">
              <button
                type="button"
                onClick={() => navigate(`/decisions/${decision.decision_id}/prep-pack`)}
                className="button button-primary button-small gap-1.5"
              >
                <Icon name="document" className="h-3.5 w-3.5" />
                Generate consultation Prep Pack
              </button>
            </div>
          </div>
        ) : (
          <div className="flex items-center justify-between pt-1">
            <span className="text-xs text-ink/60">This decision qualifies for guided resolution drafting.</span>
            <button
              type="button"
              onClick={() => navigate(`/decisions/${decision.decision_id}/resolve`)}
              className="button button-primary button-small gap-1.5"
            >
              Draft resolution response →
            </button>
          </div>
        )}
      </div>

      {/* Actionable Options */}
      <div>
        <PageHeader
          eyebrow="Your Options"
          title="Ways you can respond"
        >
          Compare each option's expected outcome, effort, and cost before deciding your move.
        </PageHeader>

        <div className="space-y-4">
          {activeOptions.map((option, idx) => (
            <div
              key={option.option_id}
              className="rounded-2xl border border-ink/10 bg-white p-6 shadow-sm hover:border-pine/40 transition-colors"
            >
              <div className="flex items-start justify-between gap-4">
                <div>
                  <span className="text-xs font-bold text-pine uppercase tracking-wider">
                    Option {idx + 1}
                  </span>
                  <h3 className="mt-1 font-display text-lg font-semibold text-ink">
                    {option.action}
                  </h3>
                </div>
                {!isEscalatedTier && (
                  <button
                    type="button"
                    onClick={() => navigate(`/decisions/${decision.decision_id}/resolve?option=${option.option_id}`)}
                    className="button button-secondary button-small shrink-0"
                  >
                    Select this move
                  </button>
                )}
              </div>

              <p className="mt-3 text-sm leading-6 text-ink/75">{option.consequence}</p>

              <div className="mt-4 flex flex-wrap items-center justify-between gap-3 pt-3 border-t border-ink/5 text-xs text-ink/60">
                <div className="flex gap-4">
                  <span><strong>Effort:</strong> {option.effort}</span>
                  <span><strong>Cost:</strong> {option.cost}</span>
                </div>
                <SourceSpans spans={option.source_spans} />
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Triggering Evidence */}
      <div className="rounded-2xl border border-ink/10 bg-paper p-6">
        <h3 className="text-xs font-bold uppercase tracking-wider text-ink/60 mb-2">
          Grounding Evidence
        </h3>
        <p className="text-xs text-ink/70">
          This decision was extracted from clause{decision.triggering_clause_ids.length > 1 ? "s" : ""}:{" "}
          <strong>{decision.triggering_clause_ids.join(", ")}</strong>.
        </p>
        <div className="mt-3">
          <button
            type="button"
            onClick={() => navigate(`/documents/${decision.document_id}/clauses`)}
            className="text-xs font-semibold text-pine underline underline-offset-2"
          >
            Inspect clauses in Clause Explorer →
          </button>
        </div>
      </div>

      <Disclaimer />
    </div>
  );
}
