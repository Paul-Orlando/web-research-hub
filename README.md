# Web Research Hub
### n8n · Replit Agent · Exa AI · Gemini 2.5 Flash · GPT-4.1

A hierarchical, three-agent web research pipeline that decomposes
a research question into parallel search subtasks, executes them
against live web sources via Exa, and synthesizes the results into
a categorized, cited one-page report — built with the Replit Agent
+ n8n workflow pattern.

---

## What It Does

Enter any topic or question. The system plans targeted search
subtasks, executes them against the web with date-range filtering,
and returns a structured report with category headers and inline
source citations — ready to copy, export as PDF, or share with a
team.

---

## Architecture

```
Replit Frontend (React + Vite + Express)
        ↓ webhook
┌─────────────────────────────────────────┐
│   1. SEARCH PLANNER                     │
│   Gemini 2.5 Flash + structured output  │
│                                          │
│   Decomposes query into 2 subtasks:     │
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
│   Gemini 2.5 Flash + structured output  │
│                                          │
│   Calls Search Worker (sub-workflow,    │
│   used as a tool) once per subtask      │
│                                          │
│   Enforces strict JSON-only output —    │
│   no prose, no markdown fences          │
│                                          │
│   Empty result → still includes entry   │
│   Total failure → returns []            │
└──────────────┬───────────────────────────┘
               ↓
        ┌──────────────────────┐
        │   SEARCH WORKER       │
        │   (sub-workflow)       │
        │                        │
        │   Exa API request      │
        │   date-range scoped    │
        │   numResults: 4        │
        │                        │
        │   Check Results (IF)   │
        │   ├─ PASS → structure  │
        │   │   search_result,   │
        │   │   source,          │
        │   │   publish_date     │
        │   └─ FAIL → graceful   │
        │       fallback message │
        └──────────────┬─────────┘
               ↓
┌─────────────────────────────────────────┐
│   3. AI SUMMARIZER                      │
│   GPT-4.1                               │
│                                          │
│   Categorizes results under headers     │
│   Summarizes per category               │
│   Cites every claim as [source](url)    │
└──────────────┬───────────────────────────┘
               ↓
        Markdown → Respond to Webhook
               ↓
        Report rendered in frontend
```

---

## Key Design Decisions

**Three agents, three single responsibilities**
Planning, execution, and synthesis are fully separated. The
Orchestrator never reasons about report structure; the Summarizer
never decides what to search. Each agent has exactly one job,
the same single-responsibility pattern used across this portfolio's
other n8n and multi-agent builds.

**Different model per stage**
Gemini 2.5 Flash handles planning and orchestration — fast,
cheap, and sufficient for structured decomposition and tool
routing. GPT-4.1 handles only the final synthesis, where
writing quality and citation formatting matter most. This
mirrors the dual-LLM cost optimization pattern used in this
portfolio's other n8n Deep Research Agent, applied here across
three stages instead of two.

**Structured output parsers, not free-text parsing**
Both the Planner and the Orchestrator use n8n's structured
output parser nodes rather than relying on the agent to format
JSON correctly through prompting alone. This is a more reliable
pattern than the prompt-only "return ONLY JSON" instructions
used in earlier workflows in this portfolio.

**Explicit edge-case handling, written into the prompt**
The Orchestrator's system prompt contains numbered rules for
empty results and total search failure — these aren't
afterthoughts, they're enforced output-format rules that prevent
the agent from breaking the JSON contract when a search returns
nothing.

**Search Worker as an isolated sub-workflow**
The Worker has no LLM call inside it at all — it's a pure,
deterministic execution unit: take structured input, call Exa,
return structured output or a graceful fallback. This keeps the
expensive reasoning concentrated in the Planner and Orchestrator,
while the high-volume execution step stays fast and cheap.

**Webhook trigger, not n8n's native chat trigger**
This workflow was built from the start to be called by an
external frontend, not used as a standalone n8n chatbot — the
webhook receives the query, the Markdown node formats the
final response, and Respond to Webhook returns it directly to
the Replit application.

---

## Tech Stack

| Layer | Technology |
|---|---|
| Frontend | React + Vite + Express (Replit Agent generated) |
| UI Components | shadcn/ui + Radix + Tailwind CSS |
| Backend Logic | n8n (3-agent hierarchical workflow) |
| Search | Exa AI (date-range filtered web search) |
| Planning / Orchestration Model | Gemini 2.5 Flash (via OpenRouter) |
| Synthesis Model | GPT-4.1 (via OpenRouter) |
| Hosting (prototype) | Replit |
| Workspace Structure | pnpm monorepo (api-server, deep-research, api-zod, db) |

---

## Workflow Files

| File | Description |
|---|---|
| [workflows/search_orchestrator.json](workflows/search_orchestrator.json) | Planner + Orchestrator + Summarizer pipeline, webhook-triggered |
| [workflows/search_worker.json](workflows/search_worker.json) | Exa search execution sub-workflow, called as a tool by the Orchestrator |

---

## Example Output

**Query:** "What are pros and cons of token usage and pricing for companies CapEx?"

The system planned 2 subtasks covering token economics and
infrastructure capital expenditure, searched both via Exa with
a date-scoped window, and returned a categorized report covering:

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

**Fixed subtask count**
The Search Planner is hardcoded to always produce exactly 2
subtasks regardless of query complexity. A simple factual
question and a broad multi-faceted topic receive the same
search depth.

**No source credibility weighting**
All sources returned by Exa are treated equally in the
synthesis step — there's no scoring that favors primary or
academic sources over secondary commentary.

**No document upload / vector search**
Despite the frontend tagline referencing document analysis,
the current pipeline is web-search only via Exa. There is no
document ingestion or vector store query path in the n8n
workflow as built.

**Replit-hosted prototype is not persistent**
The original deployment was built and hosted on Replit as
part of a DAIR.AI Replit Agent + n8n course exercise. It is
not the long-term production deployment for this portfolio.

**n8n workflow dependency**
The pipeline currently requires an active n8n instance with
configured Exa and OpenRouter credentials to run — there is
no standalone backend version yet.

---

## Roadmap

- [ ] Dynamic subtask count based on query complexity
      (Quick / Standard / Deep search depth toggle)
- [ ] Source list panel in the UI — visible, clickable list
      of every source consulted, not just inline citations
- [ ] Live progress indicator — show Planner → Orchestrator →
      Summarizer stage progress in real time
- [ ] Source credibility weighting in the synthesis step
- [ ] Document upload + vector search, to match the original
      frontend tagline
- [ ] Standalone FastAPI/Next.js rebuild — replacing the n8n
      dependency with a direct backend implementation of the
      same three-stage architecture, deployed on Railway + Vercel
      to match the rest of this portfolio

---

## Development History

This application was originally built as part of DAIR.AI's
"Building Agentic Apps with Replit Agent and n8n" course,
combining a Replit Agent-generated full-stack frontend with
an n8n-hosted, three-agent hierarchical research pipeline.

The n8n workflow files in this repository were exported
directly from the working production workflow prior to the
prototype being retired, preserving the exact system prompts,
model choices, and routing logic as built.

A standalone rebuild — replacing the n8n dependency with a
direct backend implementation — is tracked in the Roadmap
above.

---

## Related Repos

| Repo | Pattern | Framework |
|---|---|---|
| [ai-n8n-deep-research-agent](https://github.com/Paul-Orlando/ai-n8n-deep-research-agent) | Hierarchical Multi-Agent | n8n + Exa + Google Sheets |
| [ai-n8n-document-generator](https://github.com/Paul-Orlando/ai-n8n-document-generator) | LLM Chain + Quality Gate | n8n + OpenRouter |
| [deep-research-agent](https://github.com/Paul-Orlando/deep-research-agent) | Full-Stack Research App | Claude Code + Next.js + Exa |
| [ai-agent-team-supervisor-app](https://github.com/Paul-Orlando/ai-agent-team-supervisor-app) | Supervisor Pattern | OpenAI Agents SDK |

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
