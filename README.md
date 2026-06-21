# Web Research Agent

A full-stack AI research app that decomposes any query into multiple search subtasks, executes them in parallel against the web, and synthesizes a cited markdown report — all with live streaming progress.

## Architecture

Three-agent pipeline (replicated from n8n):

| Agent | Model | Role |
|---|---|---|
| Search Planner | `google/gemini-2.5-flash` | Breaks the query into 2–6 subtasks (scales with depth) |
| Search Orchestrator | — | Pure Python loop; calls Exa AI for each subtask |
| AI Summarizer | `google/gemini-2.5-flash` | Synthesizes results into a categorized, cited report |

All LLM calls route through **OpenRouter**. Web search uses the **Exa AI** API directly.

## Stack

- **Frontend**: Next.js 15 (App Router) · shadcn/ui · Tailwind CSS v4 · `react-markdown`
- **Backend**: Python FastAPI · `sse-starlette` · `httpx` · `fpdf2` · `python-docx`

## Quick Start

### Backend

```bash
cd backend
python -m venv .venv && source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp ../.env.example .env  # fill in your API keys
uvicorn main:app --reload
```

### Frontend

```bash
cd frontend
cp .env.local.example .env.local  # set NEXT_PUBLIC_API_URL
npm install
npm run dev
```

Open [http://localhost:3000](http://localhost:3000).

## Environment Variables

| Variable | Where | Description |
|---|---|---|
| `OPENROUTER_API_KEY` | backend `.env` | OpenRouter API key |
| `EXA_API_KEY` | backend `.env` | Exa AI API key |
| `NEXT_PUBLIC_API_URL` | frontend `.env.local` | Deployed backend URL |

## Search Depth

| Mode | Subtasks | Results/subtask |
|---|---|---|
| Quick | 2 | 3 |
| Standard | 3–4 | 4 |
| Deep | 5–6 | 5 |

## Deployment

### Backend → Railway

1. Create a new Railway project, point it at `/backend`
2. Set `OPENROUTER_API_KEY` and `EXA_API_KEY` in Railway env vars
3. Railway picks up `Procfile` automatically: `uvicorn main:app --host 0.0.0.0 --port $PORT`

### Frontend → Vercel

1. Create a new Vercel project, point it at `/frontend`
2. Set `NEXT_PUBLIC_API_URL` to your Railway backend URL
3. Deploy — CORS on the backend already allows `*.vercel.app`

## Model Change Note

The original n8n workflow used `openai/gpt-4.1` for the AI Summarizer step. This build uses `google/gemini-2.5-flash` for all three agents to simplify the stack to a single model family via OpenRouter.

**Potential tradeoff**: Gemini 2.5 Flash may produce slightly less structured category groupings or less precise citation formatting compared to GPT-4.1 for the synthesis step. If you notice a quality regression, change the `MODEL` constant in `backend/agents/summarizer.py` to `"openai/gpt-4.1"` — it's a one-line change and uses the same OpenRouter endpoint.

## Roadmap (not in scope for this build)

- Document upload / PDF ingestion
- Vector store / ChromaDB / document search
- Source credibility scoring
- Academic-specific APIs (arXiv, Semantic Scholar)
- Real-time streaming token output from the Summarizer
- Persistent session storage (database-backed)
