# Research Quality Evaluation

Measures how well the planner → orchestrator → summarizer pipeline grounds its
reports in the sources it actually retrieved. The pipeline is called
in-process (not through the HTTP API) against a **local** MCP server, so the
eval never touches the deployed demo server and its 10 requests/hour limit.

Evals are run by hand and never in CI.

## Setup

**1. Run the MCP server locally on port 8001** from your
`web-research-hub-mcp-server` checkout:

```bash
cd ../web-research-hub-mcp-server
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

Its local `.env` needs:

```
EXA_API_KEY=...
MCP_API_KEY=...          # any secret; must match backend/.env (step 2)
RATE_LIMIT_MAX=10000     # each search makes 2 requests; a full eval makes ~200
```

Set `RATE_LIMIT_MAX` **only in this local `.env`**, never in Railway: the
deployed demo server keeps its default of 10 requests/hour. Then start it:

```bash
uvicorn main:app --port 8001
```

Check it: `curl http://localhost:8001/health`

**2. Point the backend at it.** `backend/.env` needs `OPENROUTER_API_KEY` and
the same `MCP_API_KEY`. The eval forces `MCP_SERVER_URL=http://localhost:8001`
(override it with `--mcp-url`) and **refuses to run against any non-local
host**, even if `.env` points at the deployed server.

**3. Install the eval dependencies** (from `backend/`):

```bash
pip install -r requirements-dev.txt
```

## Running

From `backend/`:

```bash
python -m evals.run --questions 2 --runs 1   # smoke test, about $0.08
python -m evals.run                          # full: 15 questions x 3 runs, about $1.70
```

| Flag | Default | |
|---|---|---|
| `--questions N` | all | only the first N questions in `questions.yaml` |
| `--runs N` | 3 | runs per question |
| `--judge-model M` | `openai/gpt-4.1-mini` | OpenRouter model for the citation judge |
| `--max-cost USD` | 5.00 | stop once the estimated spend passes this |
| `--mcp-url URL` | `http://localhost:8001` | local MCP server |

Output: raw per-run data (plan, search results, report, metrics, judge labels,
token usage) goes to `results/<date>.json`, and the summary table below is
rewritten in place. A second run on the same day overwrites both.

## Question set

`questions.yaml` has 15 questions: factual/historical, recent news (phrased as
"the past 30 days"), comparisons, technical topics, one ambiguous question
(`expect: ambiguous`), and one false-premise question with no good answer
(`expect: no_answer`). 12 run at Quick depth and 3 at Standard.

## Metrics

| Metric | Definition |
|---|---|
| Sources | Search results with a URL, per run |
| Citation coverage | % of report units (bullets, plus sentences of non-bullet prose; headings excluded) containing a `[text](url)` citation |
| Invented sources | % of unique cited URLs not among the run's search-result URLs, after normalizing scheme, `www.`, trailing slash, fragment and `utm_*`. **Target 0%.** The offending URLs are listed in the raw JSON |
| Domains cited | Unique domains among cited URLs, per run |
| Supported / partial | An LLM judge labels up to 5 sampled (claim, cited source summary) pairs per run as supported, partial or unsupported, using the source text only. Rates are pooled across runs. Claims citing only invented URLs aren't judged; they're counted under Invented sources |
| Handling | For `no_answer` questions, and any run where every search came back empty: correct means the judge confirms the report flags the missing information **and** it cites no invented URLs. For `ambiguous` questions: whether the report acknowledges the ambiguity |
| Latency | Wall time for planner + searches + summarizer (searches run sequentially, as in the API) |
| Tokens / Cost | Planner + summarizer tokens from OpenRouter's `usage` (captured in the eval process; the app discards it). Cost = OpenRouter cost + Exa ($7/1k `auto` searches + $1/1k summary pages). Judge cost is excluded per run but included in total spend |

Before the first question, the runner sends one real search through the local
MCP server and stops if it gets nothing back. It repeats that check after any
run where every search came back empty, so a dead key stops the eval instead
of skewing it. This matters because `exa_search` returns the same fallback
entry for "no results" and for errors (bad Exa key, MCP 401, timeout), so the
eval can't tell those apart from the results alone.

Caveats: the judge sees Exa's *summary* of each page, not the full page, so a
claim that's true on the page but missing from the summary is labelled
partial or unsupported. Search results vary between runs, which is why each
question runs 3 times.

## Results

<!-- results:start -->
_Run 2026-10-22: 15 questions x 3 runs, generator `google/gemini-2.5-flash`, judge `openai/gpt-4.1-mini`, total spend $1.49. Raw data: `results/2026-10-22.json`._

| Question | Depth | Runs | Sources | Citation coverage | Invented sources | Domains cited | Supported / partial | Handling | Latency | Tokens | Cost / run |
|---|---|---|---|---|---|---|---|---|---|---|---|
| `apollo11` | quick | 3 | 6.0 | 80% | 0% | 3.3 | 100% / 0% | — | 19.2s | 4,602 | $0.0251 |
| `berlin_wall` | quick | 3 | 6.0 | 59% | 6% | 4.7 | 93% / 7% | — | 21.4s | 4,495 | $0.0257 |
| `penicillin` | standard | 3 | 13.3 | 85% | 3% | 9.0 | 93% / 7% | — | 30.2s | 7,147 | $0.0441 |
| `montreal_protocol` | quick | 3 | 6.0 | 70% | 5% | 5.7 | 100% / 0% | — | 20.0s | 5,488 | $0.0270 |
| `news_ai_regulation` | quick | 3 | 6.0 | 84% | 0% | 5.7 | 100% / 0% | — | 20.1s | 5,078 | $0.0262 |
| `news_climate` | quick | 3 | 6.0 | 77% | 0% | 5.7 | 100% / 0% | — | 22.8s | 5,215 | $0.0268 |
| `news_semiconductors` | standard | 3 | 16.0 | 79% | 0% | 12.7 | 100% / 0% | — | 43.4s | 11,051 | $0.0556 |
| `postgres_vs_mysql` | quick | 3 | 6.0 | 67% | 0% | 5.0 | 100% / 0% | — | 26.8s | 6,277 | $0.0275 |
| `heat_pump_vs_furnace` | quick | 3 | 6.0 | 67% | 6% | 6.0 | 100% / 0% | — | 25.9s | 5,997 | $0.0274 |
| `lfp_vs_nmc` | standard | 3 | 16.0 | 40% | 0% | 7.0 | 100% / 0% | — | 40.4s | 11,714 | $0.0559 |
| `rust_vs_go` | quick | 3 | 6.0 | 69% | 5% | 6.0 | 100% / 0% | — | 25.6s | 6,213 | $0.0275 |
| `raft` | quick | 3 | 6.0 | 70% | 14% | 4.0 | 87% / 13% | — | 24.1s | 5,171 | $0.0268 |
| `crispr_editing` | quick | 3 | 6.0 | 64% | 12% | 3.7 | 93% / 7% | — | 25.6s | 5,426 | $0.0267 |
| `ambiguous_mercury` | quick | 3 | 6.0 | 74% | 0% | 4.7 | 100% / 0% | notes ambiguity 3/3 | 23.0s | 5,373 | $0.0269 |
| `no_answer_math_nobel` | quick | 3 | 6.0 | 76% | 7% | 4.0 | 87% / 13% | flags no-answer 2/3 | 18.8s | 4,050 | $0.0243 |
| **Overall** |  | 45 | 7.8 | 69% | 3% | 5.8 | 97% / 3% | flags no-answer 2/3, notes ambiguity 3/3 | 25.8s | 6,220 | $0.0316 |

```
Runs: 45 (15 questions x 3), errors: 0
Citation coverage: 69%
Invented-source rate: 3% (10 URLs)
Citation support (judge, n=220): 97% supported, 3% partial, 0% unsupported
Sources / run: 7.8, unique domains cited / run: 5.8
Empty-result subtasks: 0/106
Latency / run: 25.8s, tokens / run: 6,220, cost / run: $0.0316
Total eval spend (incl. judge): $1.49
No-answer handling: 2/3 correct
Ambiguity acknowledged: 3/3
```
<!-- results:end -->
