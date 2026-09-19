import { useState } from "react";
import type { FormEvent } from "react";
import { api } from "../api/client";
import { demoComparison } from "../api/demo";
import type { ComparisonResult } from "../api/types";
import { useWayfinder } from "../app";
import { Disclaimer, ErrorNotice, PageHeader } from "../components/ui";

export function CompareScreen() {
  const { activeDocument } = useWayfinder();
  const [docA, setDocA] = useState(activeDocument?.document_id || "");
  const [docB, setDocB] = useState("");
  const [result, setResult] = useState<ComparisonResult | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleCompare = async (e: FormEvent) => {
    e.preventDefault();
    if (!docA.trim() || !docB.trim()) {
      setError("Please enter two document IDs to compare.");
      return;
    }

    setIsLoading(true);
    setError(null);

    try {
      const data = await api.compareDocuments(docA.trim(), docB.trim());
      setResult(data);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Comparison failed. Check document IDs.");
    } finally {
      setIsLoading(false);
    }
  };

  const loadDemoComparison = () => {
    setDocA("doc_demo_v1");
    setDocB("doc_demo_v2");
    setResult(demoComparison);
    setError(null);
  };

  return (
    <div className="mx-auto max-w-4xl space-y-8">
      <PageHeader
        eyebrow="Redraft Comparison"
        title="Compare Document Versions"
      >
        See how a revised agreement alters your existing decisions, obligations, and risk levels.
      </PageHeader>

      {/* Input Form */}
      <form onSubmit={handleCompare} className="rounded-2xl border border-ink/10 bg-white p-6 shadow-sm space-y-4">
        <h2 className="text-xs font-bold uppercase tracking-wider text-ink/60">
          Select Two Documents to Compare
        </h2>

        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <div>
            <label htmlFor="doc-a" className="block text-xs font-medium text-ink/75 mb-1.5">
              Original Document ID (Version A)
            </label>
            <input
              id="doc-a"
              type="text"
              placeholder="e.g. doc_12345"
              value={docA}
              onChange={(e) => setDocA(e.target.value)}
              className="w-full rounded-lg border border-ink/20 bg-paper px-3 py-2 text-xs text-ink focus:border-pine focus:outline-none font-mono"
            />
          </div>

          <div>
            <label htmlFor="doc-b" className="block text-xs font-medium text-ink/75 mb-1.5">
              Revised Document ID (Version B)
            </label>
            <input
              id="doc-b"
              type="text"
              placeholder="e.g. doc_67890"
              value={docB}
              onChange={(e) => setDocB(e.target.value)}
              className="w-full rounded-lg border border-ink/20 bg-paper px-3 py-2 text-xs text-ink focus:border-pine focus:outline-none font-mono"
            />
          </div>
        </div>

        {error && <ErrorNotice message={error} />}

        <div className="flex flex-wrap items-center justify-between gap-3 pt-2">
          <button
            type="submit"
            disabled={isLoading || !docA || !docB}
            className="button button-primary button-small"
          >
            {isLoading ? "Comparing…" : "Compare versions"}
          </button>

          <button
            type="button"
            onClick={loadDemoComparison}
            className="button button-secondary button-small text-xs"
          >
            Load sample contract redraft (Scenario B)
          </button>
        </div>
      </form>

      {/* Results */}
      {result && (
        <div className="space-y-6">
          {/* Decision Impact Summary Banner */}
          <div className="rounded-2xl border-2 border-pine/30 bg-sage/35 p-6 shadow-sm">
            <span className="text-xs font-bold uppercase tracking-wider text-pine">
              Decision Impact Summary
            </span>
            <p className="mt-2 font-display text-xl font-semibold text-ink">
              {result.decision_impact_summary}
            </p>
          </div>

          {/* Clause Diffs */}
          <div className="space-y-4">
            <h2 className="text-sm font-semibold uppercase tracking-wider text-ink/70">
              Clause-by-Clause Changes
            </h2>

            {result.clause_diffs.map((diff, idx) => {
              const statusTheme =
                diff.status === "changed"
                  ? "badge-warn"
                  : diff.status === "added"
                  ? "badge-safe"
                  : diff.status === "removed"
                  ? "badge-danger"
                  : "badge-neutral";

              const riskTheme =
                diff.risk_delta === "increased"
                  ? "text-red-700 bg-red-50 border border-red-200"
                  : diff.risk_delta === "decreased"
                  ? "text-emerald-700 bg-emerald-50 border border-emerald-200"
                  : "text-ink/60 bg-paper border border-ink/10";

              return (
                <article
                  key={idx}
                  className="rounded-2xl border border-ink/10 bg-white p-6 shadow-sm space-y-4"
                >
                  <div className="flex flex-wrap items-center justify-between gap-2 border-b border-ink/5 pb-3">
                    <div className="flex items-center gap-2">
                      <span className="font-semibold text-sm capitalize text-ink">
                        {diff.clause_type.replace(/_/g, " ")}
                      </span>
                      <span className={`badge ${statusTheme} uppercase tracking-wider`}>
                        {diff.status}
                      </span>
                    </div>

                    {diff.risk_delta && (
                      <span className={`px-2.5 py-1 rounded-full text-xs font-semibold ${riskTheme}`}>
                        Risk: {diff.risk_delta}
                      </span>
                    )}
                  </div>

                  <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
                    <div className="rounded-xl bg-paper/60 p-4 space-y-1.5 border border-ink/5">
                      <span className="text-[11px] font-bold uppercase tracking-wider text-ink/50">
                        Version A (Original)
                      </span>
                      <p className="text-xs leading-relaxed text-ink/80">
                        {diff.before || "None (Clause added in Version B)"}
                      </p>
                    </div>

                    <div className="rounded-xl bg-paper/60 p-4 space-y-1.5 border border-ink/5">
                      <span className="text-[11px] font-bold uppercase tracking-wider text-pine">
                        Version B (Revised)
                      </span>
                      <p className="text-xs leading-relaxed text-ink/80">
                        {diff.after || "None (Clause deleted in Version B)"}
                      </p>
                    </div>
                  </div>
                </article>
              );
            })}
          </div>
        </div>
      )}

      <Disclaimer />
    </div>
  );
}
