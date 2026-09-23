# Wayfinder

> Don't summarize the document. Show me my move.

[![Live Demo](https://img.shields.io/badge/Live%20Demo-Wayfinder%20App-0D9488?style=for-the-badge&logo=render)](https://wayfinder-vpyc.onrender.com)
[![API Docs](https://img.shields.io/badge/FastAPI-Docs-009688?style=for-the-badge&logo=fastapi)](https://wayfinder-vpyc.onrender.com/docs)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg?style=for-the-badge)](https://opensource.org/licenses/MIT)

- **Live Application**: [https://wayfinder-vpyc.onrender.com](https://wayfinder-vpyc.onrender.com)
- **API Documentation**: [https://wayfinder-vpyc.onrender.com/docs](https://wayfinder-vpyc.onrender.com/docs)
- **Health Check**: [https://wayfinder-vpyc.onrender.com/health](https://wayfinder-vpyc.onrender.com/health)

---

Wayfinder turns a document into a ranked **Decision Record**: the real choices
it creates, their deadlines, the documented consequence of doing nothing, and
the safest next step. It is an information and preparation tool, not a source
of legal advice.

## What is included

- Upload and local PDF/TXT ingestion, clause extraction, and a deterministic
  document graph.
- Decision extraction with a schema-enforced inaction branch for every
  deadline. The consequence path is traversed from the graph; the model only
  turns that known path into plain language.
- Deterministic triage with server-side blocking of drafted artifacts for
  `lawyer_now` decisions.
- Draft resolution templates, Prep Packs, document comparison, grounded Q&A,
  deadline tracking, ICS export, and a WhatsApp-ready webhook stub.
- A React + TypeScript decision-first interface, including all primary screens
  from the product specification.

## Run locally

Start the API (from `wayfinder/backend`):

```bash
.venv/bin/python -m uvicorn app.main:app --reload
```

The API uses a local SQLite database at `data/wayfinder.db` and an
offline deterministic LLM stub by default. No API key is required to walk
through the demo. To use an OpenAI-compatible endpoint instead, set
`WAYFINDER_LLM_PROVIDER=openai`, `OPENAI_API_KEY`, and optionally
`OPENAI_BASE_URL` / `WAYFINDER_MODEL` before starting the API.

Start the web app (from `wayfinder/frontend`):

```bash
npm install
npm run dev
```

The frontend targets `http://localhost:8000` by default; set
`VITE_API_BASE_URL` to use a different API origin.

## Verify

```bash
cd backend
.venv/bin/python -m pytest
```

The `tests/golden_set/` directory contains the three running scenarios from
the specification: notice-to-vacate, freelance-contract redraft, and
arbitration opt-out.

## Deploy for Free

The repository contains a multi-stage `Dockerfile` and `render.yaml` configured to build the React SPA and serve it directly from FastAPI as a unified full-stack service with 0 extra configuration.

### Option 1: Render.com (100% Free, 1-Click)
1. Go to [dashboard.render.com](https://dashboard.render.com) and sign in with GitHub (Free, no credit card required).
2. Click **New +** → **Web Service**.
3. Select your repository `https://github.com/namanraii/WayFinder`.
4. Render will detect the `Dockerfile` automatically. Select the **Free** instance type and click **Deploy Web Service**.
5. Once built, your app will be live at `https://wayfinder-xxxx.onrender.com`.

### Option 2: Koyeb / Railway / Fly.io (Free Tier)
1. Import `https://github.com/namanraii/WayFinder.git`.
2. Select Docker deployment (it will use the root `Dockerfile` on port `8080`).

### Option 3: Google Cloud Run (Free Tier)
```bash
gcloud run deploy wayfinder \
  --source . \
  --region us-central1 \
  --allow-unauthenticated
```


## Resource Efficiency & Performance Architecture

Wayfinder is designed for high computational and memory efficiency, adhering to strict resource utilization best practices:

### 1. Time Complexity & Algorithmic Optimization
- **Batch Database Operations**: Replaced repetitive single-row queries with bulk `batch_insert` (`conn.executemany`) and batch updates across clause segmentation, graph generation, decision extraction, and deadline syncing, reducing database round-trips from $O(N)$ to $O(1)$.
- **In-Memory Graph Construction**: Document graph nodes and edges are assembled entirely in memory before two batch insertion passes, eliminating nested $O(N^2)$ SQL lookups.
- **Compiled Pattern Matching**: All regular expressions for headings, dates, currency, and clause classification are precompiled at module load time rather than inside request loops.
- **Bounded Text Sampling**: Heuristic classifiers (e.g. language detection) operate on fixed-window prefix samples ($O(1)$ time complexity), preventing processing delays on large legal documents.

### 2. Memory Utilization & Allocation
- **Thread-Local Connection Pooling**: Reuses one open SQLite connection per worker thread with WAL mode and 256 MB memory-mapped I/O (`PRAGMA mmap_size`), eliminating connection teardown overhead and memory fragmentation.
- **Paginated Collection APIs**: Endpoints (`/documents/{id}/clauses`, `/documents/{id}/decisions`, `/users/{id}/tracker`) provide `limit` and `offset` query parameters, ensuring bounded memory footprint regardless of document size.
- **Generator Stream Processing**: `query_iter` yields rows lazily to avoid materializing large query result sets in RAM.

### 3. Multi-Tier Caching
- **Server-Side In-Memory Cache**: `functools.lru_cache` caches disk prompt templates and clause classification hits.
- **HTTP Response Caching**: GET endpoints include client-validating `Cache-Control: private, max-age=...` directives and gzip compression middleware.
- **Client-Side Request Cache**: Frontend API client provides an in-memory TTL query cache to prevent redundant HTTP requests during navigation.

### 4. Frontend Rendering Efficiency
- **Component Memoization**: List item components (`DecisionCard`, `ClauseItem`, `TrackerRow`) are wrapped in `React.memo` with `useCallback` event handlers to avoid unnecessary React virtual-DOM re-renders.
- **Code-Splitting & Lazy Loading**: All screen views use `React.lazy()` with route-level chunking, keeping the initial JS bundle payload minimal.

---

## Safety design

- No jurisdiction is silently assumed. Unknown jurisdiction produces the
  required disclosure and can only make triage more cautious.
- The app never files, sends, or represents on a user's behalf.
- Every model generation is schema-validated, guardrailed before persistence,
  and recorded in an audit log with prompt and model versions.
- Major outputs always carry the product disclaimer.

See [the full product specification](docs/wayfinder_full.md) for contracts,
guardrails, and implementation details.

