import { useEffect, useMemo, useState } from "react";
import { api } from "../api/client";
import { demoTrackerEntries } from "../api/demo";
import type { DeadlineTrackerEntry } from "../api/types";
import { navigate, useWayfinder } from "../app";
import {
  Disclaimer,
  EmptyState,
  ErrorNotice,
  Icon,
  LoadingState,
  PageHeader,
  daysUntil,
  formatDate,
} from "../components/ui";

export function DeadlineTrackerScreen() {
  const { userId } = useWayfinder();
  const [entries, setEntries] = useState<DeadlineTrackerEntry[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [downloadingId, setDownloadingId] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    async function loadTracker() {
      setIsLoading(true);
      setError(null);

      try {
        const data = await api.getTracker(userId);
        if (!cancelled) setEntries(data);
      } catch (err: unknown) {
        // Fallback to demo tracker
        if (!cancelled) {
          setEntries(demoTrackerEntries);
        }
      } finally {
        if (!cancelled) setIsLoading(false);
      }
    }

    loadTracker();
    return () => {
      cancelled = true;
    };
  }, [userId]);

  const sortedEntries = useMemo(() => {
    return [...entries].sort((a, b) => {
      return (a.deadline || "").localeCompare(b.deadline || "");
    });
  }, [entries]);

  const handleDownloadIcs = async (trackerId: string) => {
    setDownloadingId(trackerId);
    try {
      const blob = await api.downloadCalendar(trackerId);
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `deadline_${trackerId}.ics`;
      a.click();
      URL.revokeObjectURL(url);
    } catch {
      // If backend export fails, generate a client-side ICS blob as fallback
      const entry = entries.find((e) => e.tracker_id === trackerId);
      if (entry) {
        const dateVal = entry.deadline.replace(/-/g, "");
        const icsContent = [
          "BEGIN:VCALENDAR",
          "VERSION:2.0",
          "PRODID:-//Wayfinder//Deadline Tracker//EN",
          "BEGIN:VEVENT",
          `UID:${trackerId}@wayfinder.local`,
          `DTSTART;VALUE=DATE:${dateVal}`,
          `SUMMARY:${entry.resolving_action || "Wayfinder Legal Deadline"}`,
          `DESCRIPTION:${entry.inaction_consequence_short || ""}`,
          "END:VEVENT",
          "END:VCALENDAR",
        ].join("\r\n");
        const fallbackBlob = new Blob([icsContent], { type: "text/calendar;charset=utf-8" });
        const fallbackUrl = URL.createObjectURL(fallbackBlob);
        const a = document.createElement("a");
        a.href = fallbackUrl;
        a.download = `deadline_${trackerId}.ics`;
        a.click();
        URL.revokeObjectURL(fallbackUrl);
      }
    } finally {
      setDownloadingId(null);
    }
  };

  if (isLoading) {
    return <LoadingState label="Loading your tracked deadlines…" />;
  }

  return (
    <div className="mx-auto max-w-4xl space-y-8">
      <PageHeader
        eyebrow="Deadline Tracker"
        title="Your Critical Dates"
      >
        Every decision with a document-stated deadline is tracked here with its default outcome if missed.
      </PageHeader>

      {error && <ErrorNotice message={error} />}

      {entries.length === 0 ? (
        <EmptyState
          title="No open deadlines tracked"
          detail="Upload a document or notice to automatically detect and track response deadlines."
          action={
            <button
              type="button"
              onClick={() => navigate("/upload")}
              className="button button-primary button-small"
            >
              Upload document
            </button>
          }
        />
      ) : (
        <div className="space-y-4">
          {sortedEntries.map((entry) => {
            const daysRemaining = daysUntil(entry.deadline);
            const isUrgent = daysRemaining !== null && daysRemaining <= 7;
            const isOverdue = daysRemaining !== null && daysRemaining < 0;

            return (
              <article
                key={entry.tracker_id}
                className="rounded-2xl border border-ink/10 bg-white p-6 shadow-card flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between"
              >
                <div className="space-y-2 max-w-xl">
                  <div className="flex flex-wrap items-center gap-2">
                    <span
                      className={`badge ${
                        isOverdue ? "badge-danger" : isUrgent ? "badge-danger" : "badge-safe"
                      }`}
                    >
                      <Icon name="clock" className="h-3 w-3 mr-1" />
                      {isOverdue ? "Passed" : isUrgent ? "Due Soon" : "Open"} ·{" "}
                      {formatDate(entry.deadline)}
                      {daysRemaining !== null &&
                        ` (${isOverdue ? `${Math.abs(daysRemaining)}d ago` : `${daysRemaining}d left`})`}
                    </span>
                    <span className="badge badge-neutral">
                      Reminders: {entry.reminder_schedule.join(", ")}
                    </span>
                  </div>

                  <h3 className="font-display text-lg font-bold text-ink">
                    {entry.resolving_action || "Required Action"}
                  </h3>

                  {entry.inaction_consequence_short && (
                    <p className="text-xs text-red-900/90 bg-red-50/80 p-2.5 rounded-lg border border-red-200/50">
                      <strong>If missed:</strong> {entry.inaction_consequence_short}
                    </p>
                  )}
                </div>

                <div className="flex sm:flex-col gap-2 shrink-0">
                  <button
                    type="button"
                    onClick={() => handleDownloadIcs(entry.tracker_id)}
                    disabled={downloadingId === entry.tracker_id}
                    className="button button-secondary button-small gap-1.5"
                  >
                    <Icon name="calendar" className="h-3.5 w-3.5" />
                    {downloadingId === entry.tracker_id ? "Exporting…" : "Add to Calendar (.ics)"}
                  </button>

                  <button
                    type="button"
                    onClick={() => navigate(`/decisions/${entry.decision_id}`)}
                    className="button button-primary button-small gap-1.5"
                  >
                    View options →
                  </button>
                </div>
              </article>
            );
          })}
        </div>
      )}

      <Disclaimer />
    </div>
  );
}
