import { useEffect, useState } from "react";
import { api } from "../api/client";
import { demoArtifact } from "../api/demo";
import type { ResolutionArtifact } from "../api/types";
import { navigate } from "../app";
import { BackLink, Disclaimer, ErrorNotice, Icon, LoadingState, PageHeader } from "../components/ui";

export function ResolutionWorkspaceScreen({
  decisionId,
  optionId,
}: {
  decisionId: string;
  optionId?: string;
}) {
  const [artifact, setArtifact] = useState<ResolutionArtifact | null>(null);
  const [content, setContent] = useState("");
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);
  const [fieldValues, setFieldValues] = useState<Record<string, string>>({});

  useEffect(() => {
    let cancelled = false;

    async function generate() {
      setIsLoading(true);
      setError(null);

      try {
        const result = await api.resolveDecision(decisionId, optionId || "opt_a");
        if (!cancelled) {
          setArtifact(result);
          setContent(result.content);
        }
      } catch (err: unknown) {
        // Check if blocked by tier gate (403)
        const msg = err instanceof Error ? err.message : "Draft generation failed.";
        if (msg.includes("403") || msg.toLowerCase().includes("blocked")) {
          if (!cancelled) {
            setError(
              "Resolution drafting is blocked for this decision because it carries high stakes or irreversible consequences. Wayfinder does not generate self-serve letters for this tier. Please prepare a consultation pack instead."
            );
          }
        } else if (decisionId.includes("demo")) {
          if (!cancelled) {
            setArtifact(demoArtifact);
            setContent(demoArtifact.content);
          }
        } else {
          if (!cancelled) setError(msg);
        }
      } finally {
        if (!cancelled) setIsLoading(false);
      }
    }

    generate();
    return () => {
      cancelled = true;
    };
  }, [decisionId, optionId]);

  const handleFieldChange = (field: string, val: string) => {
    setFieldValues((prev) => ({ ...prev, [field]: val }));
    // Update content by replacing [field] placeholder
    setContent((prevContent) => {
      const token = `[${field}]`;
      if (prevContent.includes(token)) {
        return prevContent.replace(token, val);
      }
      return prevContent;
    });
  };

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(content);
      setCopied(true);
      setTimeout(() => setCopied(false), 2500);
    } catch {
      // Fallback
    }
  };

  const handleDownload = () => {
    const blob = new Blob([content], { type: "text/plain;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = `wayfinder_draft_${artifact?.type || "letter"}.txt`;
    link.click();
    URL.revokeObjectURL(url);
  };

  if (isLoading) {
    return <LoadingState label="Preparing resolution template draft…" />;
  }

  if (error) {
    return (
      <div className="mx-auto max-w-3xl space-y-6">
        <BackLink onClick={() => navigate(`/decisions/${decisionId}`)}>
          Back to decision
        </BackLink>
        <ErrorNotice
          message={error}
          action={
            <button
              type="button"
              onClick={() => navigate(`/decisions/${decisionId}/prep-pack`)}
              className="button button-primary button-small mt-2"
            >
              Generate consultation Prep Pack instead →
            </button>
          }
        />
      </div>
    );
  }

  const fieldsToFill = artifact?.fields_to_fill || [];

  return (
    <div className="mx-auto max-w-4xl space-y-8">
      <BackLink onClick={() => navigate(`/decisions/${decisionId}`)}>
        Back to decision options
      </BackLink>

      <PageHeader
        eyebrow="Resolution Workspace"
        title="Review & complete your draft"
      >
        This draft uses structured template fields derived from your document. Fill in your details, review the terms, and download or copy the message.
      </PageHeader>

      {/* Fields to Fill Panel */}
      {fieldsToFill.length > 0 && (
        <div className="rounded-2xl border border-ink/10 bg-white p-6 space-y-4 shadow-card">
          <div className="flex items-center justify-between">
            <h2 className="text-xs font-bold uppercase tracking-wider text-pine">
              Details to complete before sending
            </h2>
            <span className="badge badge-neutral">
              {fieldsToFill.length} field{fieldsToFill.length !== 1 ? "s" : ""}
            </span>
          </div>

          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            {fieldsToFill.map((field) => (
              <div key={field}>
                <label htmlFor={`field-${field}`} className="block text-xs font-medium text-ink/75 mb-1 capitalize">
                  {field.replace(/_/g, " ")}
                </label>
                <input
                  id={`field-${field}`}
                  type="text"
                  placeholder={`Enter ${field.replace(/_/g, " ")}`}
                  value={fieldValues[field] || ""}
                  onChange={(e) => handleFieldChange(field, e.target.value)}
                  className="w-full rounded-lg border border-ink/20 bg-paper px-3 py-1.5 text-xs text-ink focus:border-pine focus:outline-none"
                />
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Editor & Actions */}
      <div className="rounded-2xl border border-ink/10 bg-white p-6 shadow-card space-y-4">
        <div className="flex flex-wrap items-center justify-between gap-2 border-b border-ink/10 pb-4">
          <span className="text-xs font-semibold text-ink/70 capitalize">
            Template: {artifact?.type.replace(/_/g, " ") || "Formal Letter"}
          </span>
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={handleCopy}
              className="button button-secondary button-small gap-1.5"
            >
              <Icon name={copied ? "check" : "document"} className="h-3.5 w-3.5" />
              {copied ? "Copied to clipboard!" : "Copy text"}
            </button>
            <button
              type="button"
              onClick={handleDownload}
              className="button button-primary button-small gap-1.5"
            >
              <Icon name="download" className="h-3.5 w-3.5" />
              Download (.txt)
            </button>
          </div>
        </div>

        <label htmlFor="draft-content" className="sr-only">Editable draft text</label>
        <textarea
          id="draft-content"
          value={content}
          onChange={(e) => setContent(e.target.value)}
          rows={18}
          className="w-full font-mono text-xs leading-relaxed text-ink bg-paper/50 rounded-xl p-4 border border-ink/10 focus:border-pine focus:outline-none resize-y"
        />
      </div>

      <Disclaimer />
    </div>
  );
}
