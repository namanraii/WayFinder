import { useEffect, useMemo, useState } from "react";
import { api } from "../api/client";
import { demoClauses } from "../api/demo";
import type { Clause } from "../api/types";
import { navigate } from "../app";
import { BackLink, Disclaimer, ErrorNotice, Icon, LoadingState, PageHeader } from "../components/ui";

export function ClauseExplorerScreen({ documentId }: { documentId: string }) {
  const [clauses, setClauses] = useState<Clause[]>([]);
  const [filterType, setFilterType] = useState<string>("all");
  const [searchQuery, setSearchQuery] = useState("");
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [expandedId, setExpandedId] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    async function loadClauses() {
      setIsLoading(true);
      setError(null);

      try {
        const data = await api.getClauses(documentId);
        if (!cancelled) setClauses(data);
      } catch (err: unknown) {
        if (documentId.includes("demo")) {
          if (!cancelled) setClauses(demoClauses);
        } else {
          if (!cancelled) {
            setError(err instanceof Error ? err.message : "Failed to load clauses.");
          }
        }
      } finally {
        if (!cancelled) setIsLoading(false);
      }
    }

    loadClauses();
    return () => {
      cancelled = true;
    };
  }, [documentId]);

  const clauseTypes = useMemo(
    () => Array.from(new Set(clauses.map((c) => c.clause_type))).sort(),
    [clauses],
  );

  const filteredClauses = useMemo(() => {
    const q = searchQuery.trim().toLowerCase();
    return clauses.filter((c) => {
      if (filterType !== "all" && c.clause_type !== filterType) return false;
      if (q) {
        const match =
          (c.clause_title || "").toLowerCase().includes(q) ||
          (c.plain_language || "").toLowerCase().includes(q) ||
          c.original_text.toLowerCase().includes(q);
        if (!match) return false;
      }
      return true;
    });
  }, [clauses, filterType, searchQuery]);

  if (isLoading) {
    return <LoadingState label="Loading extracted document clauses…" />;
  }

  if (error) {
    return (
      <div className="mx-auto max-w-3xl space-y-4">
        <BackLink onClick={() => navigate(`/documents/${documentId}/decisions`)}>
          Back to decisions
        </BackLink>
        <ErrorNotice message={error} />
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-4xl space-y-8">
      <BackLink onClick={() => navigate(`/documents/${documentId}/decisions`)}>
        Back to Decision Record
      </BackLink>

      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <PageHeader
          eyebrow="Clause Explorer"
          title="Extracted Document Clauses"
        >
          Inspect every segmented clause, plain-language translation, obligation, and risk flag.
        </PageHeader>
      </div>

      {/* Filter and Search Bar */}
      <div className="flex flex-col gap-3 rounded-2xl border border-ink/10 bg-white p-4 shadow-sm sm:flex-row sm:items-center sm:justify-between">
        <div className="flex flex-1 items-center gap-2 rounded-lg border border-ink/15 bg-paper px-3 py-1.5 text-xs">
          <Icon name="document" className="h-4 w-4 text-ink/40" />
          <input
            type="text"
            placeholder="Search clause text or summary…"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="w-full bg-transparent text-ink placeholder:text-ink/40 focus:outline-none"
          />
        </div>

        <div className="flex items-center gap-2">
          <label htmlFor="filter-type" className="text-xs text-ink/60 whitespace-nowrap">Filter type:</label>
          <select
            id="filter-type"
            value={filterType}
            onChange={(e) => setFilterType(e.target.value)}
            className="rounded-lg border border-ink/15 bg-paper px-3 py-1.5 text-xs text-ink focus:border-pine focus:outline-none"
          >
            <option value="all">All types ({clauses.length})</option>
            {clauseTypes.map((type) => (
              <option key={type} value={type}>
                {type.replace(/_/g, " ")} ({clauses.filter((c) => c.clause_type === type).length})
              </option>
            ))}
          </select>
        </div>
      </div>

      {/* Clause Cards */}
      <div className="space-y-4">
        {filteredClauses.length === 0 ? (
          <div className="rounded-2xl border border-dashed border-ink/20 p-8 text-center text-xs text-ink/60">
            No clauses match your search criteria.
          </div>
        ) : (
          filteredClauses.map((clause) => {
            const isExpanded = expandedId === clause.clause_id;
            return (
              <article
                key={clause.clause_id}
                className="rounded-2xl border border-ink/10 bg-white p-6 shadow-sm space-y-4"
              >
                <div className="flex flex-wrap items-center justify-between gap-2 border-b border-ink/5 pb-3">
                  <div className="flex items-center gap-2">
                    <span className="font-mono text-xs font-bold text-pine">
                      {clause.clause_id}
                    </span>
                    <span className="badge badge-neutral capitalize">
                      {clause.clause_type.replace(/_/g, " ")}
                    </span>
                  </div>

                  <div className="flex items-center gap-3 text-xs text-ink/55">
                    {clause.page && <span>Page {clause.page}</span>}
                    <span>{(clause.extraction_confidence * 100).toFixed(0)}% confidence</span>
                  </div>
                </div>

                {clause.clause_title && (
                  <h3 className="font-display text-lg font-semibold text-ink">
                    {clause.clause_title}
                  </h3>
                )}

                {clause.plain_language && (
                  <div className="rounded-xl bg-sage/35 p-4 text-xs leading-relaxed text-ink/85">
                    <strong className="text-pine font-semibold uppercase tracking-wider block mb-1">
                      Plain Language Summary
                    </strong>
                    {clause.plain_language}
                  </div>
                )}

                {/* Risks & Missing Elements */}
                {clause.risks && clause.risks.length > 0 && (
                  <div className="space-y-1.5">
                    <span className="text-[11px] font-bold uppercase tracking-wider text-red-800">
                      Risk Flags
                    </span>
                    <div className="flex flex-wrap gap-2">
                      {clause.risks.map((risk, i) => (
                        <span
                          key={i}
                          className={`badge ${
                            risk.severity === "high" ? "badge-danger" : "badge-warn"
                          }`}
                        >
                          {risk.type}: {risk.description}
                        </span>
                      ))}
                    </div>
                  </div>
                )}

                {clause.missing_elements && clause.missing_elements.length > 0 && (
                  <div className="text-xs text-ink/65">
                    <span className="font-semibold text-ink/75">Missing elements: </span>
                    {clause.missing_elements.join(", ")}
                  </div>
                )}

                {/* Toggle Original Text */}
                <div className="pt-2">
                  <button
                    type="button"
                    onClick={() => setExpandedId(isExpanded ? null : clause.clause_id)}
                    className="text-xs font-semibold text-pine underline underline-offset-2"
                  >
                    {isExpanded ? "Hide original contract text" : "View original contract text"}
                  </button>

                  {isExpanded && (
                    <div className="mt-3 rounded-lg border border-ink/10 bg-paper p-4 font-mono text-xs leading-relaxed text-ink/80 whitespace-pre-wrap">
                      {clause.original_text}
                    </div>
                  )}
                </div>
              </article>
            );
          })
        )}
      </div>

      <Disclaimer />
    </div>
  );
}
