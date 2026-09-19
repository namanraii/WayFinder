import { useState } from "react";
import type { FormEvent } from "react";
import { api } from "../api/client";
import { DEMO_DOCUMENT_ID } from "../api/demo";
import { navigate, useWayfinder } from "../app";
import { Disclaimer, ErrorNotice, Icon, PageHeader } from "../components/ui";

const ROLE_OPTIONS = [
  { value: "tenant", label: "Tenant (housing, lease, notice)" },
  { value: "freelancer", label: "Freelancer / Contractor (client agreement, invoices)" },
  { value: "consumer", label: "Consumer (terms of service, refund policy)" },
  { value: "employee", label: "Employee (employment agreement, offer letter)" },
  { value: "borrower", label: "Borrower / Debt (loan agreement, collection notice)" },
  { value: "general", label: "General party to this document" },
];

export function UploadScreen() {
  const { userId, setActiveDocument, useDemo } = useWayfinder();
  const [file, setFile] = useState<File | null>(null);
  const [roleContext, setRoleContext] = useState("tenant");
  const [country, setCountry] = useState("IN");
  const [stateOrRegion, setStateOrRegion] = useState("");
  const [trainingOptIn, setTrainingOptIn] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [dragOver, setDragOver] = useState(false);

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    if (!file) {
      setErrorMessage("Please select a document file (.pdf or .txt) to upload.");
      return;
    }

    setIsSubmitting(true);
    setErrorMessage(null);

    try {
      const doc = await api.uploadDocument(file, {
        userId,
        roleContext,
        country: country.trim() || undefined,
        stateOrRegion: stateOrRegion.trim() || undefined,
        trainingOptIn,
      });

      setActiveDocument(doc);
      navigate(`/documents/${doc.document_id}/decisions`);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Document processing failed. Please try again.";
      setErrorMessage(msg);
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="mx-auto max-w-2xl">
      <PageHeader
        eyebrow="Document Intake"
        title="Upload your document"
      >
        Wayfinder analyzes what the document requires from you: deadlines, options, and what happens if you don't act.
      </PageHeader>

      <form onSubmit={handleSubmit} className="space-y-6">
        {/* File Dropzone */}
        <div
          onDragOver={(e) => {
            e.preventDefault();
            setDragOver(true);
          }}
          onDragLeave={() => setDragOver(false)}
          onDrop={(e) => {
            e.preventDefault();
            setDragOver(false);
            if (e.dataTransfer.files?.[0]) {
              setFile(e.dataTransfer.files[0]);
            }
          }}
          className={`relative flex flex-col items-center justify-center rounded-2xl border-2 border-dashed p-8 text-center transition-colors ${
            dragOver
              ? "border-pine bg-sage/30"
              : file
              ? "border-pine/40 bg-white"
              : "border-ink/20 bg-white/70 hover:border-pine/40"
          }`}
        >
          <input
            id="file-input"
            type="file"
            accept=".pdf,.txt,.md"
            onChange={(e) => e.target.files?.[0] && setFile(e.target.files[0])}
            className="absolute inset-0 cursor-pointer opacity-0"
            aria-label="Select legal document to upload"
          />
          <Icon name="document" className="h-10 w-10 text-pine" />
          <div className="mt-3 text-sm">
            {file ? (
              <div>
                <p className="font-semibold text-ink">{file.name}</p>
                <p className="text-xs text-ink/60">{(file.size / 1024).toFixed(1)} KB — click or drop to replace</p>
              </div>
            ) : (
              <div>
                <span className="font-semibold text-pine">Choose a PDF or text file</span> or drag it here
                <p className="mt-1 text-xs text-ink/50">PDF, TXT, MD up to 25MB</p>
              </div>
            )}
          </div>
        </div>

        {/* Role Selection */}
        <div className="rounded-2xl border border-ink/10 bg-white p-6 space-y-4">
          <h2 className="text-sm font-semibold uppercase tracking-wider text-ink/60">Your Context</h2>
          
          <div>
            <label htmlFor="role-context" className="block text-xs font-medium text-ink/75 mb-1.5">
              Who are you in relation to this document?
            </label>
            <select
              id="role-context"
              value={roleContext}
              onChange={(e) => setRoleContext(e.target.value)}
              className="w-full rounded-lg border border-ink/20 bg-paper px-3 py-2 text-sm text-ink focus:border-pine focus:outline-none"
            >
              {ROLE_OPTIONS.map((opt) => (
                <option key={opt.value} value={opt.value}>
                  {opt.label}
                </option>
              ))}
            </select>
          </div>

          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <div>
              <label htmlFor="country" className="block text-xs font-medium text-ink/75 mb-1.5">
                Country (optional)
              </label>
              <input
                id="country"
                type="text"
                value={country}
                onChange={(e) => setCountry(e.target.value)}
                placeholder="e.g. IN, US, UK"
                className="w-full rounded-lg border border-ink/20 bg-paper px-3 py-2 text-sm text-ink focus:border-pine focus:outline-none"
              />
            </div>
            <div>
              <label htmlFor="region" className="block text-xs font-medium text-ink/75 mb-1.5">
                State / Region (optional)
              </label>
              <input
                id="region"
                type="text"
                value={stateOrRegion}
                onChange={(e) => setStateOrRegion(e.target.value)}
                placeholder="e.g. Tamil Nadu, California"
                className="w-full rounded-lg border border-ink/20 bg-paper px-3 py-2 text-sm text-ink focus:border-pine focus:outline-none"
              />
            </div>
          </div>
        </div>

        {/* Privacy & Consent */}
        <div className="rounded-2xl border border-ink/10 bg-white p-6 space-y-3">
          <h2 className="text-sm font-semibold uppercase tracking-wider text-ink/60">Privacy & Consent</h2>
          <label className="flex items-start gap-3 text-xs text-ink/70 cursor-pointer">
            <input
              type="checkbox"
              checked={trainingOptIn}
              onChange={(e) => setTrainingOptIn(e.target.checked)}
              className="mt-0.5 rounded border-ink/30 text-pine focus:ring-pine"
            />
            <span>
              Opt-in to allow anonymized document data to help improve legal analysis accuracy (default is off).
            </span>
          </label>
        </div>

        {errorMessage && <ErrorNotice message={errorMessage} />}

        <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between pt-2">
          <button
            type="submit"
            disabled={isSubmitting || !file}
            className="button button-primary"
          >
            {isSubmitting ? "Analyzing document…" : "Analyze decisions"}
          </button>

          <button
            type="button"
            onClick={() => {
              useDemo();
              navigate(`/documents/${DEMO_DOCUMENT_ID}/decisions`);
            }}
            className="button button-secondary text-xs"
          >
            Or view sample eviction notice
          </button>
        </div>
      </form>

      <div className="mt-10">
        <Disclaimer compact />
      </div>
    </div>
  );
}
