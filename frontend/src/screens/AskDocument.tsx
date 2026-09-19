import { useState } from "react";
import type { FormEvent } from "react";
import { api } from "../api/client";
import type { AskResponse } from "../api/types";
import { navigate } from "../app";
import { BackLink, ConfidenceBadge, Disclaimer, ErrorNotice, PageHeader } from "../components/ui";

interface Message {
  id: string;
  sender: "user" | "assistant";
  text: string;
  citations?: any[];
  confidence?: "high" | "medium" | "low";
  linkedDecisionId?: string | null;
}

const SAMPLE_QUESTIONS = [
  "What is my deadline to respond?",
  "What happens if I do nothing?",
  "Who is responsible for repairs or payments?",
  "Can I request an extension?",
];

export function AskDocumentScreen({ documentId }: { documentId: string }) {
  const [messages, setMessages] = useState<Message[]>([
    {
      id: "welcome",
      sender: "assistant",
      text: "I am grounded strictly in this document. Ask any question about your deadlines, obligations, or consequences.",
    },
  ]);
  const [question, setQuestion] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleAsk = async (queryText: string) => {
    const q = queryText.trim();
    if (!q) return;

    const userMsg: Message = {
      id: `u_${Date.now()}`,
      sender: "user",
      text: q,
    };

    setMessages((prev) => [...prev, userMsg]);
    setQuestion("");
    setIsLoading(true);
    setError(null);

    try {
      const resp: AskResponse = await api.askDocument(documentId, q);
      const assistantMsg: Message = {
        id: `a_${Date.now()}`,
        sender: "assistant",
        text: resp.answer,
        citations: resp.citations,
        confidence: resp.confidence,
        linkedDecisionId: (resp as any).linked_decision_id,
      };
      setMessages((prev) => [...prev, assistantMsg]);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Failed to answer question.");
    } finally {
      setIsLoading(false);
    }
  };

  const onSubmit = (e: FormEvent) => {
    e.preventDefault();
    handleAsk(question);
  };

  return (
    <div className="mx-auto max-w-3xl space-y-6">
      <BackLink onClick={() => navigate(`/documents/${documentId}/decisions`)}>
        Back to Decision Record
      </BackLink>

      <PageHeader
        eyebrow="Ask Your Document"
        title="Grounded Document Q&A"
      >
        Answers are drawn strictly from your extracted clauses and obligations, with source citations.
      </PageHeader>

      {/* Suggested prompts */}
      <div className="flex flex-wrap gap-2">
        {SAMPLE_QUESTIONS.map((sq) => (
          <button
            key={sq}
            type="button"
            onClick={() => handleAsk(sq)}
            disabled={isLoading}
            className="rounded-full border border-ink/15 bg-white px-3 py-1.5 text-xs text-ink/75 hover:border-pine hover:text-pine transition-colors"
          >
            {sq}
          </button>
        ))}
      </div>

      {/* Message Thread */}
      <div className="space-y-4 rounded-2xl border border-ink/10 bg-white p-6 shadow-card min-h-96 flex flex-col justify-between">
        <div className="space-y-4 overflow-y-auto max-h-[500px]">
          {messages.map((msg) => (
            <div
              key={msg.id}
              className={`flex flex-col ${
                msg.sender === "user" ? "items-end" : "items-start"
              }`}
            >
              <div
                className={`max-w-[85%] rounded-2xl p-4 text-xs sm:text-sm leading-relaxed ${
                  msg.sender === "user"
                    ? "bg-pine text-white"
                    : "bg-paper text-ink border border-ink/10"
                }`}
              >
                <p className="whitespace-pre-wrap">{msg.text}</p>

                {/* Citations & Badges for Assistant Responses */}
                {msg.sender === "assistant" && (
                  <div className="mt-3 flex flex-wrap items-center gap-2 pt-2 border-t border-ink/10 text-xs">
                    {msg.confidence && <ConfidenceBadge confidence={msg.confidence} />}
                    {msg.citations && msg.citations.length > 0 && (
                      <div className="flex flex-wrap gap-1">
                        {msg.citations.map((c: any, i: number) => {
                          const id = typeof c === "string" ? c : c?.clause_id || "clause";
                          return (
                            <span key={i} className="source-pill">
                              {id}
                            </span>
                          );
                        })}
                      </div>
                    )}
                    {msg.linkedDecisionId && (
                      <button
                        type="button"
                        onClick={() => navigate(`/decisions/${msg.linkedDecisionId}`)}
                        className="text-xs font-semibold text-pine underline underline-offset-2 ml-auto"
                      >
                        View related decision →
                      </button>
                    )}
                  </div>
                )}
              </div>
            </div>
          ))}

          {isLoading && (
            <div className="flex items-center gap-2 text-xs text-ink/60 p-2">
              <span className="loading-dot !h-4 !w-4 !border-2" />
              Retrieving grounded answer…
            </div>
          )}
        </div>

        {error && <ErrorNotice message={error} />}

        {/* Input Bar */}
        <form onSubmit={onSubmit} className="pt-4 border-t border-ink/10 flex gap-2">
          <input
            type="text"
            placeholder="Ask a question about this document…"
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
            disabled={isLoading}
            className="flex-1 rounded-xl border border-ink/20 bg-paper px-4 py-2.5 text-xs sm:text-sm text-ink focus:border-pine focus:outline-none"
          />
          <button
            type="submit"
            disabled={isLoading || !question.trim()}
            className="button button-primary button-small px-4"
          >
            Ask
          </button>
        </form>
      </div>

      <Disclaimer />
    </div>
  );
}
