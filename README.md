[![CI](https://github.com/Paul-Orlando/web-research-hub/actions/workflows/ci.yml/badge.svg)](https://github.com/Paul-Orlando/web-research-hub/actions/workflows/ci.yml)

# Web Research Hub
### Next.js · FastAPI · OpenRouter · Gemini 2.5 Flash · Exa AI · MCP

A hierarchical, three-agent web research pipeline that decomposes
a research question into parallel search subtasks, executes them
against live web sources via Exa, and synthesizes the results into
a categorized, cited report — with a live source panel, real-time
progress tracking, and export to PDF, DOCX, and Markdown.

---

## 🔗 Live Demo

**[Try it live → web-research-hub.vercel.app](https://web-research-hub.vercel.app/)**

---

## What It Does

Enter any topic or question and choose a search depth — Quick,
Standard, or Deep. The system plans targeted search subtasks,
executes them against the web with date-range filtering, and
streams a structured report back in real time, with every source
visible in a live-updating panel as it's found. Ask a follow-up
question in the same session, or export the final report as PDF,
DOCX, or Markdown.

---

## Architecture

```
Web Research Agent (Vercel/Next.js)
         ↓ SSE stream
FastAPI Orchestrator (Railway)
         ↓ MCP Streamable HTTP
Web Research Hub MCP Server (Railway)
         ↓
     Exa AI (web_search)
     httpx + BS4 (fetch_url)
     fpdf2/python-docx (export_report)
```

### Internal Pipeline

```
FastAPI Orchestrator
        │
┌─────────────────────────────────────────┐
│   1. SEARCH PLANNER                     │
│   OpenRouter — google/gemini-2.5-flash  │
│                                          │
│   Decomposes query into N subtasks      │
│   (count driven by search depth):       │
│   id, query, source_type, time_period,  │
│   domain_focus, priority (1-5)          │
│                                          │
│   Infers start_date / end_date from     │
│   time_period — never future-dated,     │
│   "recent" = minimum 14 day window      │
└──────────────┬───────────────────────────┘
               ↓
┌─────────────────────────────────────────┐
│   2. SEARCH ORCHESTRATOR                │
│   Pure Python — no LLM call             │
│                                          │
│   Loops through subtasks, routing each  │
│   to the MCP Server via Streamable HTTP │
│                                          │
│   numResults scaled by search depth     │
│   Empty result → entry still included   │
│   Streams subtask_complete events live  │
└──────────────┬───────────────────────────┘
               ↓
        ┌──────────────────────────┐
        │  WEB RESEARCH HUB MCP    │
        │  SERVER                  │
        │                          │
        │  web_search — Exa API    │
        │  fetch_url — httpx+BS4   │
        │  export_report — fpdf2 / │
        │  python-docx             │
        │                          │
        │  Never throws —          │
        │  graceful fallback       │
        │  on zero results         │
        └──────────────┬───────────┘
               ↓
┌─────────────────────────────────────────┐
│   3. AI SUMMARIZER                      │
│   OpenRouter — google/gemini-2.5-flash  │
│                                          │
│   Categorizes results under headers     │
│   Summarizes per category               │
│   Sees numbered sources (no URLs),      │
│   cites every claim as [S1], [S1][S4]   │
└──────────────┬───────────────────────────┘
               ↓
┌─────────────────────────────────────────┐
│   4. CITATION GUARD                     │
│   Pure Python — server-side check       │
│                                          │
│   Maps each [Sn] to the real            │
│   [domain](url) the search returned     │
│   Unknown ID, raw URL or low            │
│   coverage → one summarizer retry       │
│   Still invalid → citation removed,     │
│   claim marked (unverified)             │
└──────────────┬───────────────────────────┘
               ↓
        SSE: report event (+ guard stats) → frontend renders
        Source List Panel built directly from
        Orchestrator results (not the Summarizer)
```

---

## Key Features

- **Three-agent pipeline** — Planner, Orchestrator, Summarizer,
  each with one job
- **Search Depth Toggle** — Quick (2 subtasks) / Standard (3-4) /
  Deep (5-6), directly controlling subtask count and result depth
- **Live progress indicator** — real-time stage updates as the
  pipeline plans, searches, and synthesizes
- **Source List Panel** — live-updating list of every source
  consulted, built directly from search results rather than
  re-parsed from the final report, so it can never break even
  if report formatting varies
- **Multi-turn sessions** — ask follow-up questions without
  losing prior context; previous reports stay visible and
  collapsible
- **Export** — Markdown, PDF, and DOCX, with citations rendered
  as visible source domains so they remain meaningful outside
  the browser
- **Clear button** — full session reset with one click, no page
  reload
- **SSE streaming** — the frontend receives live pipeline events,
  not just a final result
- **MCP tool layer** — search and export operations route through
  the Web Research Hub MCP Server, making the tool layer
  independently reusable by any MCP-compatible client
- **Citation guard** — the Summarizer cites numbered sources and
  the server maps them to real links, so no report shows a URL the
  search step didn't return; invalid citations are retried, then
  removed
- **Measured, not assumed** — a 45-run research quality eval with
  an LLM judge, plus a mocked pytest suite and GitHub Actions CI

---

## Key Design Decisions

**Three agents, three single responsibilities**
Planning, execution, and synthesis are fully separated. The
Orchestrator never reasons about report structure; the Summarizer
never decides what to search. Each agent has exactly one job,
the same single-responsibility pattern used across this
portfolio's other multi-agent builds.

**Orchestrator is deterministic, not an LLM call**
In the original n8n prototype, orchestration was handled by an
agent node calling a sub-workflow as a tool. In this rebuild,
that step is a plain Python loop calling the MCP Server directly
— faster, cheaper, and removes an unnecessary LLM call from a
step that was always purely mechanical.

**Source List Panel built from search results, not re-parsed
from the Summarizer's output**
The source list is built directly from the Orchestrator's
collected results before the Summarizer ever runs, so a
formatting slip in the final report can never break source
attribution.

**Search Depth Toggle replaces the original fixed subtask count**
The n8n prototype always created exactly 2 subtasks regardless
of query complexity. The rebuild fixes this directly: Quick,
Standard, and Deep modes scale both subtask count and
per-subtask result count.

**Single model family via OpenRouter**
The n8n prototype split work across Gemini 2.5 Flash (planning,
orchestration) and GPT-4.1 (synthesis only). This rebuild
simplifies to Gemini 2.5 Flash across all LLM calls via
OpenRouter. If synthesis quality is ever noticeably weaker,
the Summarizer model can be swapped back via a one-line change
in `summarizer.py`.

**Citations are verified in code, not trusted from the prompt**
The Summarizer never sees or writes a URL. It gets the search
results as a numbered source list (`[S1]` title, domain, date,
summary) and cites claims by ID, leaving out any claim no listed
source supports. A server-side citation guard maps each ID to the
real `[domain](url)` link, so every link in a report is a URL the
Orchestrator actually returned. An earlier version let the model
copy URLs itself, and the eval found it mis-copying long ones (an
extra digit in an article ID, `.com` for `.org`). An ID that
doesn't exist, a raw URL that slips through, or a report with too
few citations gets one Summarizer retry; anything still invalid
is removed and the claim is marked (unverified). The low-coverage
retry always lets the model drop unsupported claims: asking only
for more citations made it invent sources. With IDs the eval saw
no invented citations in 45 first drafts and no retries, and
queries got faster (19.5 s vs 26.6 s) and 10% cheaper.

**Citations render as visible domains in exported documents**
Exports render citations as `claim text (domain.com)` so the
source remains identifiable even outside the live app.

**MCP Server as the tool layer**
The backend no longer calls Exa directly. All search and export
calls route through the Web Research Hub MCP Server via MCP
Streamable HTTP. This makes the tool layer independently
reusable by any MCP-compatible client — not just this app. The
MCP server is a separate deployable service at
[github.com/Paul-Orlando/web-research-hub-mcp-server](https://github.com/Paul-Orlando/web-research-hub-mcp-server).

---

## Tech Stack

| Layer | Technology |
|---|---|
| Frontend | Next.js + shadcn/ui + Tailwind CSS |
| Backend | Python FastAPI |
| LLM Provider | OpenRouter (google/gemini-2.5-flash) |
| Search | Exa AI (via Web Research Hub MCP Server) |
| MCP Server | Web Research Hub MCP Server (Streamable HTTP) |
| Streaming | SSE (Server-Sent Events) |
| Export | fpdf2 (PDF), python-docx (DOCX) |
| Testing | pytest (all external calls mocked) + GitHub Actions CI |
| Evaluation | 45-run eval, GPT-4.1 mini as judge |
| Frontend Hosting | Vercel |
| Backend Hosting | Railway |
| Built With | Claude Code |

---

## Agent Configuration

| Agent | Model | Role |
|---|---|---|
| Search Planner | google/gemini-2.5-flash | Decomposes query into N subtasks based on search depth |
| Search Orchestrator | — (pure Python) | Routes each subtask to the MCP Server via Streamable HTTP |
| AI Summarizer | google/gemini-2.5-flash | Categorizes, summarizes, and cites all results |

---

## Search Depth Modes

| Mode | Subtasks | Results per Subtask |
|---|---|---|
| Quick | 2 | 3 |
| Standard | 3-4 | 4 |
| Deep | 5-6 | 5 |

---

## API Endpoints

| Method | Path | Description |
|---|---|---|
| `GET` | `/health` | Status check |
| `POST` | `/research` | SSE stream — query, depth_mode, session_id |
| `GET` | `/session/{session_id}/sources` | Structured source list |
| `GET` | `/session/{session_id}/history` | Prior queries in this session |
| `GET` | `/download-report/{session_id}/{format}` | Export: md, pdf, docx |
| `DELETE` | `/session/{session_id}` | Clear session |

---

## Project Structure

```
web-research-hub/
│
├── frontend/                   Next.js application
│   ├── app/                    App Router pages
│   ├── components/
│   │   ├── DepthToggle.tsx     Quick / Standard / Deep
│   │   ├── SearchBar.tsx
│   │   ├── ClearButton.tsx
│   │   ├── ProgressPanel.tsx   live stage + subtask status
│   │   ├── SourceListPanel.tsx live-updating source list
│   │   ├── ReportDisplay.tsx   markdown render + export
│   │   └── ConversationHistory.tsx
│   └── lib/
│       └── api.ts              SSE client + REST helpers
│
├── backend/                    FastAPI + agent logic
│   ├── main.py                 FastAPI app, CORS, SSE routes
│   ├── agents/
│   │   ├── planner.py
│   │   ├── orchestrator.py
│   │   ├── summarizer.py
│   │   └── citation_guard.py   maps source IDs to links, checks URLs
│   ├── tools/
│   │   └── exa_search.py       MCP client → Web Research Hub
│   │                           MCP Server (Streamable HTTP)
│   ├── models/
│   │   └── schemas.py
│   ├── session_store.py
│   ├── tests/                  pytest suite (mocked)
│   ├── evals/                  research quality eval + results
│   ├── requirements.txt
│   ├── requirements-dev.txt    test/eval dependencies
│   ├── Procfile
│   └── .env.example
│
├── .github/workflows/ci.yml    backend tests + frontend lint/build
│
├── workflows/                  Original n8n prototype (archived)
│   ├── search_orchestrator.json
│   └── search_worker.json
│
├── examples/                   Sample output
│   ├── README.md
│   ├── search_output.pdf       CapEx / token usage report
│   ├── example_report.pdf      OpenAI news report (also .md, .docx)
│   └── example_01.jpg, example_02.jpg
│
├── .env.example
├── .gitignore
└── README.md
```

---

## Quick Start

### Backend

```bash
cd backend
python -m venv .venv && source .venv/bin/activate
# Windows: .venv\Scripts\activate

pip install -r requirements.txt
cp .env.example .env
# Add your OPENROUTER_API_KEY, MCP_SERVER_URL and MCP_API_KEY to .env

uvicorn main:app --reload
```

Backend runs at `http://localhost:8000`

### Frontend

```bash
cd frontend
echo "NEXT_PUBLIC_API_URL=http://localhost:8000" > .env.local

npm install
npm run dev
```

Frontend runs at `http://localhost:3000`

---

## Testing

The backend has a pytest suite in `backend/tests/` covering the planner,
orchestrator, MCP search client, summarizer, and API endpoints. All
external calls (OpenRouter, MCP server) are mocked, so no API keys or
network access are needed.

```bash
cd backend
pip install -r requirements-dev.txt
pytest
```

Test dependencies live in `requirements-dev.txt`, so Railway's install of
`requirements.txt` stays lean. GitHub Actions runs the backend tests plus
the frontend's `npm run lint` and `npm run build` on every push and pull
request to `main`.

---

## Evaluation

`backend/evals/` holds a research quality eval: 15 questions (factual,
recent news, comparisons, technical, one ambiguous, one false premise),
each run 3 times through the real pipeline against a local MCP server, with
an LLM judge checking whether cited sources support the claims. Setup,
metric definitions and the full per-question table are in
[`backend/evals/README.md`](backend/evals/README.md).

Each eval is 45 pipeline runs (Gemini 2.5 Flash, judge GPT-4.1 mini). Three
configurations so far: no guard; guard v2, a server-side check of every
visible URL with one retry and removal of anything still invented; and ID
citations, where the summarizer cites numbered sources and the backend maps
them to links (see
[Citations are verified in code](#key-design-decisions)):

| Metric | No guard (2026-10-22) | Guard v2 (2026-10-23) | ID citations (2026-10-23) |
|---|---|---|---|
| Invented sources shown to reader | 2% (5 URLs in 5 runs) | 0% | **0%** |
| Invented citations in the model's first draft | 5 in 5 runs | 7 in 6 runs | **0** |
| Citation coverage (bullets/sentences with a citation) | 69% | 72% | **84%** |
| Report units (bullets/sentences) per run | 32.6 | 30.6 | 29.7 |
| Citation support (judge, sampled claims) | 97% (n=220) | 97% (n=225) | **99%** (n=225) |
| Claims marked (unverified) | 0 | 10 | **0** |
| False-premise question flagged instead of answered | 2/3 | 3/3 | 3/3 |
| Ambiguous question acknowledged | 3/3 | 3/3 | 3/3 |
| Latency / cost per query | 25.8 s · $0.0316 | 26.6 s · $0.0328 | **19.5 s · $0.0294** |
| Guard retries | — | 12/45 | **0/45** |

All 5 invented URLs in the no-guard run were mis-copies of real results (an
extra digit, `.com` for `.org`, a doubled word), and guard v2's coverage retry
made the model invent 8 URLs on one question. Handing the model IDs instead
of URLs removed both problems. One trade-off: reports are about as long on
average, but `raft` and `heat_pump_vs_furnace` came out 24-32% shorter, so
part of their coverage gain comes from dropping uncited claims.

Per question, cost ranges from about $0.023–0.026 at Quick depth to about
$0.046–0.053 at Standard. The
[eval README](backend/evals/README.md#citation-guard-and-id-citations) has
the full per-question tables, the classification of each invented URL, and
the guard's history, including parsing bugs in its first version that the
eval caught.

---

## Environment Variables

### Backend (`backend/.env`)

| Variable | Required | Description |
|---|---|---|
| `OPENROUTER_API_KEY` | ✅ | OpenRouter API key for all LLM calls |
| `MCP_SERVER_URL` | ✅ | URL of the Web Research Hub MCP Server |
| `MCP_API_KEY` | ✅ | Auth key for the MCP Server — must match the key set on the MCP server |
| `CORS_ORIGIN_REGEX` | optional | Default: `https://.*\.vercel\.app` |

### Frontend (`frontend/.env.local`)

| Variable | Required | Description |
|---|---|---|
| `NEXT_PUBLIC_API_URL` | ✅ | Backend URL — do NOT mark as Sensitive in Vercel |

---

## Deployment

### Backend → Railway

1. New project → Deploy from GitHub repo
2. Set Root Directory: `backend`
3. Add environment variables:
   `OPENROUTER_API_KEY`, `MCP_SERVER_URL`, `MCP_API_KEY`

   `EXA_API_KEY` is set on the MCP server, not here.
4. Procfile already configured:
```
web: uvicorn main:app --host 0.0.0.0 --port $PORT
```
5. Generate domain in Settings → Networking

### Frontend → Vercel

1. Import repo → set Root Directory: `frontend`
2. Add environment variable:
```
NEXT_PUBLIC_API_URL = https://your-railway-url.up.railway.app
```
⚠️ **Critical:** Do NOT mark `NEXT_PUBLIC_API_URL` as Sensitive.

3. Deploy

---

## Deployment Notes

**CORS configuration**
The backend uses `allow_origin_regex` to whitelist all
`*.vercel.app` domains automatically.

**NEXT_PUBLIC_ variables**
Baked into the JavaScript bundle at build time. If marked
Sensitive in Vercel, the value won't be available during the
build step and requests will fail.

**MCP_API_KEY must match on both services**
The Web Research Hub backend passes `MCP_API_KEY` as an
`X-API-Key` header on every call to the MCP Server. Both
Railway services must have the same key value set — if they
differ, every search will return a 401 Unauthorized error.

---

## Example Output

**Query:** "What are pros and cons of token usage and pricing for companies CapEx?"

Generated during the original n8n prototype phase. The system
planned 2 subtasks, searched both via Exa with a date-scoped
window, and returned a categorized report covering:

- AI Token Cost Benchmarks and Spending Patterns
- Risks and Dangers of Token-based Billing
- Strategic Recommendations for Token Usage
- AI Tokens in Decentralized Systems
- Capital Expenditure (CapEx) Trends in AI Infrastructure

Each section cites named sources with figures pulled directly
from the search results — not generated from model memory.

Full example report: [examples/search_output.pdf](examples/search_output.pdf)

---

## Known Limitations

**No source credibility weighting**
All sources returned by Exa are treated equally — there's no
scoring that favors primary sources over secondary commentary.

**No document upload / vector search**
The current pipeline is web-search only via Exa. There is no
document ingestion or vector store query path.

**Single LLM provider**
All three agent calls route through OpenRouter using a single
model. There's no automatic fallback if OpenRouter or the
underlying model is unavailable.

**MCP Server rate limited to 10 requests per IP per hour**
One search generates approximately 4-5 MCP calls internally
(MCP handshake + one tool call per subtask), allowing roughly
2 complete Quick searches per hour on the demo server. Because
every call comes from the backend, this limit is shared by all
visitors to the live demo rather than applied per visitor. For
unrestricted use, self-host the MCP server with your own API
keys — see
[web-research-hub-mcp-server](https://github.com/Paul-Orlando/web-research-hub-mcp-server)
for deployment instructions.

---

## Roadmap

- [ ] Source credibility weighting in the synthesis step
- [ ] Document upload + vector search (ChromaDB) — draw on
      both live web results and uploaded documents
- [ ] Academic search — add a dedicated academic source type
      routing subtasks to an arXiv/Semantic Scholar API,
      exposed as an additional tool in the MCP Server
- [ ] Real-time streaming token output from the Summarizer
- [ ] Persistent, database-backed session storage

---

## Development History

**Phase 1 — n8n + Replit prototype**
Originally built as part of DAIR.AI's "Building Agentic Apps
with Replit Agent and n8n" course, combining a Replit Agent-
generated full-stack frontend with an n8n-hosted, three-agent
hierarchical research pipeline. The n8n workflow files are
preserved in the `workflows/` folder.

**Phase 2 — Standalone rebuild**
Rebuilt as a direct FastAPI + Next.js application, removing the
n8n runtime dependency entirely while preserving the same
three-agent architecture, system prompts, and routing logic.
Added the Search Depth Toggle, live Source List Panel, real-time
progress streaming, multi-turn sessions, and document export —
closing every gap identified in Phase 1's Known Limitations.

**Phase 3 — MCP integration**
Introduced the Web Research Hub MCP Server as the tool layer,
replacing direct Exa API calls in the backend. All web search
and export operations now route through the MCP server via
Streamable HTTP, making the tool layer independently reusable
by any MCP-compatible client. Added API key authentication
and sliding-window rate limiting (10 requests/IP/hour) to
the MCP server.

**Phase 4 — Tests, evaluation and citation guard (current)**
Added a mocked pytest suite and GitHub Actions CI, then a
45-run research quality eval with an LLM judge. The baseline
showed occasional invented citations (5 URLs in 45 runs) and one
report with no citations at all, so a server-side citation guard
was added. The eval also caught bugs in the guard's first version
(it stripped real URLs containing parentheses), which were fixed
and re-measured. The invented URLs turned out to be mis-copies of
real results, so the Summarizer now cites numbered source IDs and
the guard maps them to links: citation coverage rose from 72% to
84% (CRISPR from 56% to 80%) with no invented citations.

---

## Related Repos

| Repo | Pattern | Framework |
|---|---|---|
| [web-research-hub-mcp-server](https://github.com/Paul-Orlando/web-research-hub-mcp-server) | MCP Server | FastAPI + FastMCP |
| [ai-n8n-deep-research-agent](https://github.com/Paul-Orlando/ai-n8n-deep-research-agent) | Hierarchical Multi-Agent | n8n + Exa + Google Sheets |
| [ai-n8n-document-generator](https://github.com/Paul-Orlando/ai-n8n-document-generator) | LLM Chain + Quality Gate | n8n + OpenRouter |
| [ai-agent-team-supervisor-app](https://github.com/Paul-Orlando/ai-agent-team-supervisor-app) | Supervisor Pattern | OpenAI Agents SDK |
| [pinecone-mcp-server](https://github.com/Paul-Orlando/pinecone-mcp-server) | Custom MCP Server | Node.js + Pinecone |

---

## Author

Paul Orlando
Creative Technologist | AI Agent Developer | Data Analytics
🌐 [paulforlando.com](https://www.paulforlando.com) &nbsp;|&nbsp;
💼 [LinkedIn](https://www.linkedin.com/in/paul-orlando-7841b5154) &nbsp;|&nbsp;
🐙 [GitHub](https://github.com/Paul-Orlando)

---

## License

MIT License
