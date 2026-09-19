import { createContext, useContext, useEffect, useMemo, useState } from "react";
import type { ReactNode } from "react";
import type { DocumentRecord } from "./api/types";
import { DEMO_DOCUMENT_ID, DEMO_USER_ID, demoDocument } from "./api/demo";
import { AppShell } from "./components/AppShell";
import { AskDocumentScreen } from "./screens/AskDocument";
import { ClauseExplorerScreen } from "./screens/ClauseExplorer";
import { CompareScreen } from "./screens/Compare";
import { DeadlineTrackerScreen } from "./screens/DeadlineTracker";
import { DecisionDetailScreen } from "./screens/DecisionDetail";
import { DecisionRecordScreen } from "./screens/DecisionRecord";
import { PrepPackViewScreen } from "./screens/PrepPackView";
import { ResolutionWorkspaceScreen } from "./screens/ResolutionWorkspace";
import { UploadScreen } from "./screens/Upload";

const ACTIVE_DOCUMENT_KEY = "wayfinder.active-document";
const USER_KEY = "wayfinder.user-id";

interface WayfinderContextValue {
  activeDocument: DocumentRecord | null;
  userId: string;
  setActiveDocument: (document: DocumentRecord | null) => void;
  setUserId: (userId: string) => void;
  useDemo: () => void;
}

const WayfinderContext = createContext<WayfinderContextValue | null>(null);

function initialDocument(): DocumentRecord | null {
  try {
    const saved = window.localStorage.getItem(ACTIVE_DOCUMENT_KEY);
    return saved ? (JSON.parse(saved) as DocumentRecord) : null;
  } catch {
    return null;
  }
}

function initialUserId(): string {
  try {
    return window.localStorage.getItem(USER_KEY) || DEMO_USER_ID;
  } catch {
    return DEMO_USER_ID;
  }
}

export function WayfinderProvider({ children }: { children: ReactNode }) {
  const [activeDocument, setActiveDocumentState] = useState<DocumentRecord | null>(initialDocument);
  const [userId, setUserIdState] = useState(initialUserId);

  const setActiveDocument = (document: DocumentRecord | null) => {
    setActiveDocumentState(document);
    try {
      if (document) window.localStorage.setItem(ACTIVE_DOCUMENT_KEY, JSON.stringify(document));
      else window.localStorage.removeItem(ACTIVE_DOCUMENT_KEY);
    } catch {
      // Local storage enhancement
    }
  };

  const setUserId = (value: string) => {
    const normalized = value.trim() || DEMO_USER_ID;
    setUserIdState(normalized);
    try {
      window.localStorage.setItem(USER_KEY, normalized);
    } catch {
      // Local storage enhancement
    }
  };

  const useDemo = () => {
    setUserId(DEMO_USER_ID);
    setActiveDocument(demoDocument);
  };

  const value = useMemo(
    () => ({ activeDocument, userId, setActiveDocument, setUserId, useDemo }),
    [activeDocument, userId],
  );

  return <WayfinderContext.Provider value={value}>{children}</WayfinderContext.Provider>;
}

export function useWayfinder(): WayfinderContextValue {
  const context = useContext(WayfinderContext);
  if (!context) throw new Error("useWayfinder must be used inside WayfinderProvider");
  return context;
}

export function navigate(path: string): void {
  const normalized = path.startsWith("/") ? path : `/${path}`;
  window.location.hash = normalized;
}

export function useHashRoute(): string {
  const [route, setRoute] = useState(() => window.location.hash.slice(1) || "/upload");

  useEffect(() => {
    const onChange = () => setRoute(window.location.hash.slice(1) || "/upload");
    window.addEventListener("hashchange", onChange);
    return () => window.removeEventListener("hashchange", onChange);
  }, []);

  return route;
}

export function openDemoDecisionRecord(): void {
  navigate(`/documents/${DEMO_DOCUMENT_ID}/decisions`);
}

export function App() {
  const fullRoute = useHashRoute();
  const [pathPart, queryPart] = fullRoute.split("?");
  const queryParams = new URLSearchParams(queryPart || "");

  let content: ReactNode = null;

  const docDecisionsMatch = pathPart.match(/^\/documents\/([^/]+)\/decisions$/);
  const docClausesMatch = pathPart.match(/^\/documents\/([^/]+)\/clauses$/);
  const docAskMatch = pathPart.match(/^\/documents\/([^/]+)\/ask$/);
  const decResolveMatch = pathPart.match(/^\/decisions\/([^/]+)\/resolve$/);
  const decPrepPackMatch = pathPart.match(/^\/decisions\/([^/]+)\/prep-pack$/);
  const decDetailMatch = pathPart.match(/^\/decisions\/([^/]+)$/);

  if (docDecisionsMatch) {
    content = <DecisionRecordScreen documentId={decodeURIComponent(docDecisionsMatch[1])} />;
  } else if (docClausesMatch) {
    content = <ClauseExplorerScreen documentId={decodeURIComponent(docClausesMatch[1])} />;
  } else if (docAskMatch) {
    content = <AskDocumentScreen documentId={decodeURIComponent(docAskMatch[1])} />;
  } else if (decResolveMatch) {
    content = (
      <ResolutionWorkspaceScreen
        decisionId={decodeURIComponent(decResolveMatch[1])}
        optionId={queryParams.get("option") || undefined}
      />
    );
  } else if (decPrepPackMatch) {
    content = <PrepPackViewScreen decisionId={decodeURIComponent(decPrepPackMatch[1])} />;
  } else if (decDetailMatch) {
    content = <DecisionDetailScreen decisionId={decodeURIComponent(decDetailMatch[1])} />;
  } else if (pathPart === "/compare") {
    content = <CompareScreen />;
  } else if (pathPart === "/tracker") {
    content = <DeadlineTrackerScreen />;
  } else {
    content = <UploadScreen />;
  }

  return <AppShell>{content}</AppShell>;
}
