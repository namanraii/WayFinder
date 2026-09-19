# Wayfinder

> Don't summarize the document. Show me my move.

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


## Safety design

- No jurisdiction is silently assumed. Unknown jurisdiction produces the
  required disclosure and can only make triage more cautious.
- The app never files, sends, or represents on a user's behalf.
- Every model generation is schema-validated, guardrailed before persistence,
  and recorded in an audit log with prompt and model versions.
- Major outputs always carry the product disclaimer.

See [the full product specification](docs/wayfinder_full.md) for contracts,
guardrails, and implementation details.
