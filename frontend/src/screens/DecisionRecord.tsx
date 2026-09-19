import { useEffect, useState } from "react";
import { api } from "../api/client";
import { demoDecisions, demoDocument } from "../api/demo";
import type { DecisionSummary, DocumentRecord } from "../api/types";
import { navigate, useWayfinder } from "../app";
import { DecisionCard } from "../components/DecisionCard";
import { Disclaimer, EmptyState, ErrorNotice, Icon, LoadingState, PageHeader } from "../components/ui";

export function DecisionRecordScreen({ documentId }: { documentId: string }) {
  const { activeDocument, setActiveDocument } = useWayfinder();
  const [document, setDocument] = useState<DocumentRecord | null>(activeDocument);
  const [decisions, setDecisions] = useState<DecisionSummary[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    async function loadData() {
      setIsLoading(true);
      setError(null);

      try {
        // Try fetching live document and decisions
        const [docData, decData] = await Promise.all([
          api.getDocument(documentId),
          api.getDecisions(documentId),
        ]);

        if (!cancelled) {
          setDocument(docData);
          setActiveDocument(docData);
          setDecisions(decData.decisions);
        }
      } catch (err: unknown) {
        // If demo document ID or backend down, fall back gracefully to demo data
        if (documentId === "doc_demo_notice" || (activeDocument && activeDocument.document_id === documentId)) {
          if (!cancelled) {
            setDocument(activeDocument || demoDocument);
            setDecisions(
              demoDecisions.map((d) => ({
                decision_id: d.decision_id,
                title: d.title,
                deadline: d.deadline,
                days_remaining: d.days_remaining,
                triage_tier: d.triage_tier,
                confidence: d.confidence,
              }))
            );
          }
        } else {
          if (!cancelled) {
            setError(err instanceof Error ? err.message : "Failed to load decisions for this document.");
          }
        }
      } finally {
        if (!cancelled) setIsLoading(false);
      }
    }

    loadData();
    return () => {
      cancelled = true;
    };
  }, [documentId, setActiveDocument]);

  if (isLoading) {
    return <LoadingState label="Analyzing document and ranking decisions…" />;
  }

  if (error) {
    return (
      <div className="mx-auto max-w-3xl space-y-4">
        <ErrorNotice message={error} />
        <button
          type="button"
          onClick={() => navigate("/upload")}
          className="button button-secondary button-small"
        >
          Upload a document
        </button>
      </div>
    );
  }

  const docTitle = document?.original_filename || "Legal Document";
  const jurisdiction = document?.jurisdiction;
  const isJurisdictionUnknown = jurisdiction?.status === "unknown";

  return (
    <div className="mx-auto max-w-4xl space-y-8">
      {/* Overview Banner */}
      <div className="rounded-2xl border border-ink/10 bg-white p-6 shadow-card">
        <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <div className="flex flex-wrap items-center gap-2 mb-2">
              <span className="badge badge-neutral uppercase tracking-wider">
                {document?.document_type?.replace("_", " ") || "Document"}
              </span>
              {jurisdiction?.state_or_region && (
                <span className="badge badge-neutral">{jurisdiction.state_or_region}</span>
              )}
              {isJurisdictionUnknown && (
                <span className="badge badge-warn">Jurisdiction unconfirmed</span>
              )}
            </div>
            <h1 className="font-display text-2xl font-bold tracking-tight text-ink sm:text-3xl">
              {docTitle}
            </h1>
            <p className="mt-1 text-sm text-ink/65">
              Role: <strong className="capitalize">{document?.role_context || "general"}</strong> ·{" "}
              {decisions.length} decision{decisions.length !== 1 ? "s" : ""} require your attention
            </p>
          </div>

          <div className="flex flex-wrap gap-2">
            <button
              type="button"
              onClick={() => navigate(`/documents/${documentId}/ask`)}
              className="button button-secondary button-small gap-1.5"
            >
              <Icon name="chat" className="h-3.5 w-3.5" /> Ask document
            </button>
            <button
              type="button"
              onClick={() => navigate(`/documents/${documentId}/clauses`)}
              className="button button-secondary button-small gap-1.5"
            >
              <Icon name="document" className="h-3.5 w-3.5" /> View clauses
            </button>
          </div>
        </div>

        {isJurisdictionUnknown && (
          <div className="mt-4 rounded-xl border border-amber-200 bg-amber-50/80 p-3.5 text-xs leading-5 text-amber-900">
            <strong>Cautious routing active:</strong> This document does not confirm your governing jurisdiction.
            Deadlines and options reflect only what the document text states, and routing tiers are kept more cautious.
          </div>
        )}
      </div>

      {/* Decision Record: The Core Ranked List */}
      <div>
        <PageHeader
          eyebrow="Decision Record"
          title="What requires your decision"
        >
          Ranked by deadline urgency. Each decision shows your move, your options, and what happens if you take no action.
        </PageHeader>

        {decisions.length === 0 ? (
          <EmptyState
            title="No urgent decisions found"
            detail="Wayfinder did not detect explicit response deadlines or decision-bearing clauses in this document."
            action={
              <button
                type="button"
                onClick={() => navigate(`/documents/${documentId}/clauses`)}
                className="button button-secondary button-small"
              >
                Inspect extracted clauses
              </button>
            }
          />
        ) : (
          <div className="space-y-5">
            {decisions.map((decision, idx) => (
              <DecisionCard
                key={decision.decision_id}
                decision={decision}
                index={idx}
                documentId={documentId}
              />
            ))}
          </div>
        )}
      </div>

      <Disclaimer />
    </div>
  );
}
