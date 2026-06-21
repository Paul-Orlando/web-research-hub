# Web Research Hub
### Next.js · FastAPI · OpenRouter · Gemini 2.5 Flash · Exa AI

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
Next.js Frontend
        ↓ SSE stream
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
│   Loops through subtasks, calling the   │
│   Exa search tool directly for each one │
│                                          │
│   numResults scaled by search depth     │
│   Empty result → entry still included   │
│   Streams subtask_complete events live  │
└──────────────┬───────────────────────────┘
               ↓
        ┌──────────────────────┐
        │   EXA SEARCH TOOL      │
        │   (pure async function)│
        │                        │
        │   Exa API request      │
        │   date-range scoped    │
        │   numResults by depth  │
        │                        │
        │   Never throws —       │
        │   graceful fallback    │
        │   on zero results      │
        └──────────────┬─────────┘
               ↓
┌─────────────────────────────────────────┐
│   3. AI SUMMARIZER                      │
│   OpenRouter — google/gemini-2.5-flash  │
│                                          │
│   Categorizes results under headers     │
│   Summarizes per category               │
│   Cites every claim as [source](url)    │
└──────────────┬───────────────────────────┘
               ↓
        SSE: report event → frontend renders
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
that step is a plain Python loop calling the Exa search function
directly — faster, cheaper, and removes an unnecessary LLM call
from a step that was always purely mechanical (call a tool N
times, collect N results).

**Source List Panel built from search results, not re-parsed
from the Summarizer's output**
Earlier designs considered having the Summarizer emit a
structured source list alongside its report. This was deliberately
avoided — the source list is now built directly from the
Orchestrator's collected results before the Summarizer ever runs,
so a formatting slip in the final report can never break source
attribution.

**Search Depth Toggle replaces the original fixed subtask count**
The n8n prototype always created exactly 2 subtasks regardless of
query complexity. This was a known limitation, documented as such
at the time. The rebuild fixes it directly: Quick, Standard, and
Deep modes scale both subtask count and per-subtask result count.

**Single model family via OpenRouter**
The n8n prototype split work across Gemini 2.5 Flash (planning,
orchestration) and GPT-4.1 (synthesis only) — a deliberate dual-
tier cost strategy. This rebuild simplifies to Gemini 2.5 Flash
across all LLM calls via OpenRouter. This is a documented
tradeoff: if synthesis quality (categorization coherence, citation
formatting) is ever noticeably weaker than the original GPT-4.1
output, the Summarizer model can be swapped back via a one-line
change in `summarizer.py`.

**Citations render as visible domains in exported documents**
Markdown links render correctly as clickable text in the browser,
but `[source](url)` syntax has no meaning once flattened into a
PDF or DOCX. Exports now render citations as `claim text
(domain.com)` so the source remains identifiable even outside
the live app.

---

## Tech Stack

| Layer | Technology |
|---|---|
| Frontend | Next.js + shadcn/ui + Tailwind CSS |
| Backend | Python FastAPI |
| LLM Provider | OpenRouter (google/gemini-2.5-flash) |
| Search | Exa AI (date-range filtered web search) |
| Streaming | SSE (Server-Sent Events) |
| Export | fpdf2 (PDF), python-docx (DOCX) |
| Frontend Hosting | Vercel |
| Backend Hosting | Railway |
| Built With | Claude Code |

---

## Agent Configuration

| Agent | Model | Role |
|---|---|---|
| Search Planner | google/gemini-2.5-flash | Decomposes query into N subtasks based on search depth |
| Search Orchestrator | — (pure Python) | Executes each subtask via the Exa search tool |
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
│   │   └── summarizer.py
│   ├── tools/
│   │   └── exa_search.py       pure async Exa call
│   ├── models/
│   │   └── schemas.py
│   ├── session_store.py
│   ├── requirements.txt
│   └── Procfile
│
├── workflow/                   Original n8n prototype (archived)
│   ├── search_orchestrator.json
│   └── search_worker.json
│
├── examples/                   Sample output
│   ├── README.md
│   └── capex_token_usage_report.pdf
│
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
cp ../.env.example .env
# Add your OPENROUTER_API_KEY and EXA_API_KEY to .env

uvicorn main:app --reload
```

Backend runs at `http://localhost:8000`

### Frontend

```bash
cd frontend
cp .env.local.example .env.local
# set NEXT_PUBLIC_API_URL to http://localhost:8000 for local dev

npm install
npm run dev
```

Frontend runs at `http://localhost:3000`

---

## Environment Variables

### Backend (`backend/.env`)

| Variable | Required | Description |
|---|---|---|
| `OPENROUTER_API_KEY` | ✅ | OpenRouter API key for all LLM calls |
| `EXA_API_KEY` | ✅ | Exa AI API key for web search |
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
3. Add `OPENROUTER_API_KEY` and `EXA_API_KEY` environment variables
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
⚠️ **Critical:** Do NOT mark `NEXT_PUBLIC_API_URL` as Sensitive —
this prevents Next.js from baking the value into the build bundle.

3. Deploy

---

## Deployment Notes

**CORS configuration**
The backend uses `allow_origin_regex` to whitelist all
`*.vercel.app` domains automatically — no manual updates
needed when Vercel generates new preview URLs.

**NEXT_PUBLIC_ variables**
Baked into the JavaScript bundle at build time. If marked
Sensitive in Vercel, the value won't be available during the
build step and requests will fail.

---

## Example Output

**Query:** "What are pros and cons of token usage and pricing for companies CapEx?"

Generated during the original n8n prototype phase. The system
planned 2 subtasks covering token economics and infrastructure
capital expenditure, searched both via Exa with a date-scoped
window, and returned a categorized report covering:

- AI Token Cost Benchmarks and Spending Patterns
- Risks and Dangers of Token-based Billing
- Strategic Recommendations for Token Usage
- AI Tokens in Decentralized Systems
- Capital Expenditure (CapEx) Trends in AI Infrastructure

Each section cites named sources (Bain & Company, Thoughtworks,
MetricDuck, Platformonomics, Dell'Oro Group) with figures pulled
directly from the search results — not generated from model
memory.

Full example report: [examples/capex_token_usage_report.pdf](examples/capex_token_usage_report.pdf)

---

## Known Limitations

**No source credibility weighting**
All sources returned by Exa are treated equally in the
synthesis step — there's no scoring that favors primary or
academic sources over secondary commentary.

**No document upload / vector search**
The current pipeline is web-search only via Exa. There is no
document ingestion or vector store query path.

**Single LLM provider**
All three agent calls route through OpenRouter using a single
model. There's no automatic fallback if OpenRouter or the
underlying model is unavailable.

---

## Roadmap

- [ ] Source credibility weighting in the synthesis step
- [ ] Document upload + vector search (ChromaDB), so research
      can draw on both live web results and uploaded documents
- [ ] MCP client integration — call the existing Pinecone
      Agentic Search MCP Server as an additional tool for
      source_type: "academic" subtasks, pulling from the
      embedded ArXiv research corpus alongside live web search
- [ ] Academic-specific search APIs (arXiv, Semantic Scholar)
- [ ] Real-time streaming token output from the Summarizer,
      rather than waiting for the full report to complete
- [ ] Persistent, database-backed session storage — current
      sessions are in-memory and reset on backend restart

---

## Development History

**Phase 1 — n8n + Replit prototype**
Originally built as part of DAIR.AI's "Building Agentic Apps
with Replit Agent and n8n" course, combining a Replit Agent-
generated full-stack frontend with an n8n-hosted, three-agent
hierarchical research pipeline. The n8n workflow files are
preserved in the `workflow/` folder, exported directly from the
working production workflow prior to the prototype being retired.

**Phase 2 — Standalone rebuild (current)**
Rebuilt as a direct FastAPI + Next.js application, removing the
n8n runtime dependency entirely while preserving the same
three-agent architecture, system prompts, and routing logic.
This phase added the Search Depth Toggle, live Source List
Panel, real-time progress streaming, multi-turn sessions, and
document export — closing every gap identified in Phase 1's
Known Limitations.

---

## Related Repos

| Repo | Pattern | Framework |
|---|---|---|
| [ai-n8n-deep-research-agent](https://github.com/Paul-Orlando/ai-n8n-deep-research-agent) | Hierarchical Multi-Agent | n8n + Exa + Google Sheets |
| [ai-n8n-document-generator](https://github.com/Paul-Orlando/ai-n8n-document-generator) | LLM Chain + Quality Gate | n8n + OpenRouter |
| [deep-research-agent](https://github.com/Paul-Orlando/deep-research-agent) | Full-Stack Research App | Claude Code + Next.js + Exa |
| [ai-agent-team-supervisor-app](https://github.com/Paul-Orlando/ai-agent-team-supervisor-app) | Supervisor Pattern | OpenAI Agents SDK |
| [pinecone-mcp-server](https://github.com/Paul-Orlando/pinecone-mcp-server) | Custom MCP Server | Node.js + Pinecone |

---

## Author

Paul Orlando
Creative Technologist | AI Agent Developer | Data Analytics
🌐 [paulforlando.com](https://www.paulforlando.com)
💼 [LinkedIn](https://www.linkedin.com/in/paul-orlando-7841b5154)
🐙 [GitHub](https://github.com/Paul-Orlando)

---

## License

MIT License
