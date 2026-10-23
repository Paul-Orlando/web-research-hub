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
python -m evals.run --questions 2 --runs 1   # smoke test, about $0.05
python -m evals.run                          # full: 15 questions x 3 runs, about $1.50
```

Actual cost of the first full run was $1.49: $0.40 OpenRouter (pipeline +
judge) and $1.09 Exa. The citation guard adds one summarizer call for each
run it retries.

| Flag | Default | |
|---|---|---|
| `--questions N` | all | only the first N questions in `questions.yaml` |
| `--runs N` | 3 | runs per question |
| `--judge-model M` | `openai/gpt-4.1-mini` | OpenRouter model for the citation judge |
| `--max-cost USD` | 5.00 | stop once the estimated spend passes this |
| `--mcp-url URL` | `http://localhost:8001` | local MCP server |
| `--no-guard` | off | skip the citation guard and score raw summarizer output |
| `--tag T` | none | write `results/<date>-<T>.json` instead of `results/<date>.json` |
| `--compare-to FILE` | none | earlier results file (relative to `evals/`); writes the before/after table |

Output: raw per-run data (plan, search results, report, metrics, judge labels,
token usage) goes to `results/<date>.json`, and the summary table below is
rewritten in place. A second run on the same day overwrites both (use `--tag`
to keep them apart).

After a change to the scoring code, re-score saved runs without any API calls
(judge labels, cost and latency are kept as recorded):

```bash
python -m evals.rescore results/2026-10-22.json results/2026-10-22-guard.json
```

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
| Invented sources | % of unique visible URLs (link targets, URLs in link labels, and bare URLs, which the frontend renders as links) not among the run's search-result URLs, after normalizing scheme, `www.`, trailing slash, fragment and `utm_*`. URLs with balanced parentheses are parsed whole. **Target 0%.** The offending URLs are listed in the raw JSON |
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

## Before / after: citation guard

The app's citation guard (`agents/citation_guard.py`) checks every URL in the
summarizer's report against the URLs the orchestrator returned. On a problem
it retries the summarizer once with a correction note, and if the retry still
invents URLs it removes them, leaving `(unverified)`. "After" scores the
report the user actually sees.

**This table is guard v1** (commit `71e6cd3`), and the run exposed three bugs,
fixed in `f6168ba`:

1. URLs containing parentheses (e.g. `.../S0968-0004(20)30150-X`) were cut
   at the first `)`, so real sources were flagged as invented. 7 of the 11
   retries were false alarms, and 37 real citations were stripped (34 in
   `crispr_editing`).
2. Only `[text](url)` targets were checked. Two retries came back with bare
   `[https://...]` URLs, so coverage dropped to 0% (`lfp_vs_nmc`, `raft`),
   and 3 runs still showed an invented URL as bare text.
3. Stripping kept the link label, which sometimes repeated the invented URL.

The eval's own parser had bug 1 too, so both runs below were re-scored from
their saved reports with the fixed parser (`python -m evals.rescore`). The
first run's invented count fell from 10 to 5 URLs (the other 5 were real
sources with parentheses), and v1's rose from 0 to 3 (the bare-URL leaks).
Judge labels, cost and latency are as recorded. Some zero-citation reports
happen with or without the guard (normal model variation); the v1 guard didn't
retry on low coverage, which `f6168ba` adds.

<!-- compare:start -->
_Before: `results/2026-10-22.json` (no guard, 45 runs). After: `results/2026-10-22-guard.json` (citation guard on, 45 runs). Same questions, 3 runs each; search results differ between runs._

| Question | Invented sources | Citation coverage | Cost / run | Guard retried | Links stripped |
|---|---|---|---|---|---|
| `apollo11` | 0% → 0% | 80% → 75% | $0.0251 → $0.0259 | 0/3 | 0 |
| `berlin_wall` | 6% → 0% | 59% → 69% | $0.0257 → $0.0254 | 0/3 | 0 |
| `penicillin` | 0% → 2% | 85% → 88% | $0.0441 → $0.0573 | 2/3 | 3 |
| `montreal_protocol` | 5% → 0% | 70% → 72% | $0.0270 → $0.0265 | 0/3 | 0 |
| `news_ai_regulation` | 0% → 0% | 84% → 78% | $0.0262 → $0.0267 | 0/3 | 0 |
| `news_climate` | 0% → 0% | 77% → 75% | $0.0268 → $0.0274 | 1/3 | 0 |
| `news_semiconductors` | 0% → 0% | 79% → 73% | $0.0556 → $0.0542 | 0/3 | 0 |
| `postgres_vs_mysql` | 0% → 0% | 67% → 48% | $0.0275 → $0.0266 | 0/3 | 0 |
| `heat_pump_vs_furnace` | 0% → 0% | 67% → 49% | $0.0274 → $0.0264 | 0/3 | 0 |
| `lfp_vs_nmc` | 0% → 0% | 40% → 0% | $0.0559 → $0.0529 | 1/3 | 0 |
| `rust_vs_go` | 5% → 0% | 69% → 66% | $0.0275 → $0.0276 | 0/3 | 0 |
| `raft` | 0% → 0% | 70% → 28% | $0.0268 → $0.0267 | 1/3 | 0 |
| `crispr_editing` | 6% → 0% | 64% → 47% | $0.0267 → $0.0366 | 3/3 | 34 |
| `ambiguous_mercury` | 0% → 6% | 74% → 38% | $0.0269 → $0.0295 | 1/3 | 0 |
| `no_answer_math_nobel` | 7% → 6% | 76% → 70% | $0.0243 → $0.0283 | 2/3 | 1 |
| **Overall** | 2% → 1% | 69% → 55% | $0.0316 → $0.0332 | 11/45 | 38 |
<!-- compare:end -->

## Results

<!-- results:start -->
_Run 2026-10-22: 15 questions x 3 runs, generator `google/gemini-2.5-flash`, judge `openai/gpt-4.1-mini`, citation guard on, total spend $1.56. Raw data: `results/2026-10-22-guard.json`._

| Question | Depth | Runs | Sources | Citation coverage | Invented sources | Domains cited | Supported / partial | Handling | Latency | Tokens | Cost / run |
|---|---|---|---|---|---|---|---|---|---|---|---|
| `apollo11` | quick | 3 | 6.0 | 75% | 0% | 4.0 | 93% / 7% | — | 20.6s | 5,055 | $0.0259 |
| `berlin_wall` | quick | 3 | 6.0 | 69% | 0% | 5.3 | 100% / 0% | — | 19.9s | 4,547 | $0.0254 |
| `penicillin` | standard | 3 | 16.0 | 88% | 2% | 10.3 | 100% / 0% | — | 45.3s | 13,543 | $0.0573 |
| `montreal_protocol` | quick | 3 | 6.0 | 72% | 0% | 5.0 | 100% / 0% | — | 21.5s | 5,078 | $0.0265 |
| `news_ai_regulation` | quick | 3 | 6.0 | 78% | 0% | 6.0 | 100% / 0% | — | 22.2s | 5,240 | $0.0267 |
| `news_climate` | quick | 3 | 6.0 | 75% | 0% | 5.3 | 100% / 0% | — | 21.8s | 5,894 | $0.0274 |
| `news_semiconductors` | standard | 3 | 16.0 | 73% | 0% | 13.7 | 100% / 0% | — | 36.8s | 9,679 | $0.0542 |
| `postgres_vs_mysql` | quick | 3 | 6.0 | 48% | 0% | 5.3 | 67% / 0% | — | 24.4s | 5,971 | $0.0266 |
| `heat_pump_vs_furnace` | quick | 3 | 6.0 | 49% | 0% | 4.0 | 100% / 0% | — | 23.5s | 5,355 | $0.0264 |
| `lfp_vs_nmc` | standard | 3 | 14.7 | 0% | 0% | 2.7 | — / — | — | 37.3s | 14,055 | $0.0529 |
| `rust_vs_go` | quick | 3 | 6.0 | 66% | 0% | 5.7 | 93% / 7% | — | 25.5s | 6,389 | $0.0276 |
| `raft` | quick | 3 | 6.0 | 28% | 0% | 2.3 | 100% / 0% | — | 20.8s | 6,014 | $0.0267 |
| `crispr_editing` | quick | 3 | 6.0 | 47% | 0% | 3.7 | 67% / 20% | — | 40.9s | 12,199 | $0.0366 |
| `ambiguous_mercury` | quick | 3 | 6.0 | 38% | 6% | 4.7 | 100% / 0% | notes ambiguity 3/3 | 29.4s | 6,973 | $0.0295 |
| `no_answer_math_nobel` | quick | 3 | 6.0 | 70% | 6% | 4.3 | 100% / 0% | flags no-answer 3/3 | 25.2s | 7,207 | $0.0283 |
| **Overall** |  | 45 | 7.9 | 55% | 1% | 5.5 | 94% / 3% | flags no-answer 3/3, notes ambiguity 3/3 | 27.7s | 7,546 | $0.0332 |

```
Runs: 45 (15 questions x 3), errors: 0
Citation coverage: 55%
Invented-source rate: 1% (3 URLs)
Citation support (judge, n=190): 94% supported, 3% partial, 4% unsupported
Sources / run: 7.9, unique domains cited / run: 5.5
Empty-result subtasks: 0/107
Latency / run: 27.7s, tokens / run: 7,546, cost / run: $0.0332
Total eval spend (incl. judge): $1.56
No-answer handling: 3/3 correct
Ambiguity acknowledged: 3/3
Citation guard: retried 11/45 runs, links stripped in 6 runs (38 links)
```
<!-- results:end -->
