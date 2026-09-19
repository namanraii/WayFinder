import type {
  AskResponse,
  Clause,
  ComparisonResult,
  DecisionListResponse,
  DecisionPoint,
  DeadlineTrackerEntry,
  DocumentRecord,
  PrepPack,
  ResolutionArtifact,
  UploadDetails,
} from "./types";

const API_BASE = (import.meta.env.VITE_API_BASE_URL ?? "/api").replace(/\/$/, "");

export class ApiError extends Error {
  readonly status: number;
  readonly payload: unknown;

  constructor(message: string, status: number, payload: unknown) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.payload = payload;
  }
}

function detailFromPayload(payload: unknown): string | undefined {
  if (!payload || typeof payload !== "object") return undefined;
  const detail = (payload as { detail?: unknown }).detail;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) return "We couldn't process part of the request. Please check the document and try again.";
  return undefined;
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE}${path}`, {
      ...init,
      headers: {
        Accept: "application/json",
        ...(init.headers ?? {}),
      },
    });
  } catch {
    throw new ApiError("Wayfinder could not reach the service. Check that the backend is running.", 0, null);
  }

  const contentType = response.headers.get("content-type") ?? "";
  const payload: unknown = contentType.includes("application/json")
    ? await response.json().catch(() => null)
    : await response.text().catch(() => null);

  if (!response.ok) {
    throw new ApiError(
      detailFromPayload(payload) ?? `Request failed (${response.status}). Please try again.`,
      response.status,
      payload,
    );
  }
  return payload as T;
}

export const api = {
  async uploadDocument(file: File, details: UploadDetails): Promise<DocumentRecord> {
    const form = new FormData();
    form.append("file", file);
    form.append("user_id", details.userId);
    form.append("role_context", details.roleContext);
    form.append("training_opt_in", String(details.trainingOptIn));
    if (details.country) form.append("country", details.country);
    if (details.stateOrRegion) form.append("state_or_region", details.stateOrRegion);
    return request<DocumentRecord>("/documents", { method: "POST", body: form });
  },

  getDocument(documentId: string): Promise<DocumentRecord> {
    return request<DocumentRecord>(`/documents/${encodeURIComponent(documentId)}`);
  },

  getClauses(documentId: string): Promise<Clause[]> {
    return request<Clause[]>(`/documents/${encodeURIComponent(documentId)}/clauses`);
  },

  getDecisions(documentId: string): Promise<DecisionListResponse> {
    return request<DecisionListResponse>(`/documents/${encodeURIComponent(documentId)}/decisions`);
  },

  getDecision(decisionId: string): Promise<DecisionPoint> {
    return request<DecisionPoint>(`/decisions/${encodeURIComponent(decisionId)}`);
  },

  resolveDecision(decisionId: string, optionId: string): Promise<ResolutionArtifact> {
    return request<ResolutionArtifact>(`/decisions/${encodeURIComponent(decisionId)}/resolve`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ option_id: optionId }),
    });
  },

  getArtifact(artifactId: string): Promise<ResolutionArtifact> {
    return request<ResolutionArtifact>(`/artifacts/${encodeURIComponent(artifactId)}`);
  },

  getPrepPack(decisionId: string): Promise<PrepPack> {
    return request<PrepPack>(`/decisions/${encodeURIComponent(decisionId)}/prep-pack`, { method: "POST" });
  },

  compareDocuments(documentA: string, documentB: string): Promise<ComparisonResult> {
    return request<ComparisonResult>("/documents/compare", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ document_id_a: documentA, document_id_b: documentB }),
    });
  },

  askDocument(documentId: string, question: string): Promise<AskResponse> {
    return request<AskResponse>(`/documents/${encodeURIComponent(documentId)}/ask`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question }),
    });
  },

  getTracker(userId: string): Promise<DeadlineTrackerEntry[]> {
    return request<DeadlineTrackerEntry[]>(`/users/${encodeURIComponent(userId)}/tracker`);
  },

  async downloadCalendar(trackerId: string): Promise<Blob> {
    let response: Response;
    try {
      response = await fetch(`${API_BASE}/tracker/${encodeURIComponent(trackerId)}/export.ics`);
    } catch {
      throw new ApiError("Wayfinder could not reach the service. Check that the backend is running.", 0, null);
    }
    if (!response.ok) throw new ApiError("The calendar export could not be created. Please try again.", response.status, null);
    return response.blob();
  },
};

export function apiBaseUrl(): string {
  return API_BASE;
}
