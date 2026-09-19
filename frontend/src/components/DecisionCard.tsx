import type { DecisionSummary } from "../api/types";
import { navigate } from "../app";
import { ConfidenceBadge, Icon, TriageBadge, cx, daysUntil, formatDate } from "./ui";

export function DecisionCard({ decision, index, documentId: _documentId }: { decision: DecisionSummary; index: number; documentId: string }) {
  const computedDays = decision.days_remaining ?? daysUntil(decision.deadline);
  const urgent = computedDays !== null && computedDays <= 7;
  const overdue = computedDays !== null && computedDays < 0;
  return (
    <article className={cx("decision-card", urgent && "decision-card-urgent")}>
      <div className="flex min-w-10 flex-col items-center pt-1">
        <span className="decision-number">{String(index + 1).padStart(2, "0")}</span>
        <span className="mt-2 h-full min-h-9 w-px bg-ink/10 last:hidden" />
      </div>
      <div className="min-w-0 flex-1 pb-1">
        <div className="flex flex-wrap items-center gap-2"><TriageBadge tier={decision.triage_tier} /><ConfidenceBadge confidence={decision.confidence} /></div>
        <h2 className="mt-3 font-display text-xl font-semibold tracking-[-0.025em] text-ink sm:text-2xl">{decision.title}</h2>
        <div className={cx("mt-4 inline-flex items-center gap-2 rounded-lg px-3 py-2 text-sm", urgent ? "bg-red-50 text-red-900" : "bg-sage/55 text-pine")}>
          <Icon name="calendar" className="h-4 w-4" />
          <span><strong>{overdue ? "Passed" : urgent ? "Due soon" : "Deadline"}</strong> · {formatDate(decision.deadline)}{computedDays !== null && ` (${overdue ? `${Math.abs(computedDays)} days ago` : `${computedDays} days left`})`}</span>
        </div>
        <div className="mt-4"><button type="button" className="text-sm font-semibold text-pine underline decoration-pine/35 underline-offset-4 hover:decoration-pine" onClick={() => navigate(`/decisions/${decision.decision_id}`)}>See your options <span aria-hidden="true">→</span></button></div>
      </div>
    </article>
  );
}
