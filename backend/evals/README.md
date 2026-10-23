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

The table compares no guard (2026-10-22) with the fixed guard v2 (`f6168ba`,
2026-10-23). The guard also retries once when sources exist but the report has
zero citations or under 50% coverage (`low_coverage_retry`); invented-URL and
low-coverage corrections share that single retry.

Guard v2, 45 runs: 12 retries (6 for invented URLs, 6 for low coverage), with
URLs stripped in 3 runs (10 URLs, 8 of them in `crispr_editing`). No run ended
with zero citations or under 50% coverage (no guard: 1 zero-citation run).
Latency went from 25.8 s to 26.6 s per query, and cost from $0.0316 to $0.0328
(+4%).

**Guard v1** (`71e6cd3`, results in `results/2026-10-22-guard.json`) had three
bugs, all found by its eval run:

1. URLs containing parentheses (e.g. `.../S0968-0004(20)30150-X`) were cut
   at the first `)`, so real sources were flagged as invented. 7 of 11
   retries were false alarms, and 37 real citations were stripped.
2. Only `[text](url)` targets were checked. Retries that answered with bare
   `[https://...]` URLs dropped coverage to 0%, and 3 runs still showed an
   invented URL as bare text.
3. Stripping kept the link label, which sometimes repeated the invented URL.

v1 overall: invented 1% (3 URLs), coverage 55%. The eval's scorer had bug 1
too, so the saved runs were re-scored with the fixed parser
(`python -m evals.rescore`). The no-guard run's invented count fell from 10 to
5 URLs (the other 5 were real sources with parentheses). Judge labels, cost
and latency are as recorded.

<!-- compare:start -->
_Before: `results/2026-10-22.json` (no guard, 45 runs). After: `results/2026-10-23-guard-v2.json` (citation guard on, 45 runs). Same questions, 3 runs each; search results differ between runs._

| Question | Invented sources | Citation coverage | Cost / run | Guard retried | Links stripped |
|---|---|---|---|---|---|
| `apollo11` | 0% → 0% | 80% → 80% | $0.0251 → $0.0255 | 0/3 | 0 |
| `berlin_wall` | 6% → 0% | 59% → 68% | $0.0257 → $0.0252 | 0/3 | 0 |
| `penicillin` | 0% → 0% | 85% → 86% | $0.0441 → $0.0511 | 1/3 | 0 |
| `montreal_protocol` | 5% → 0% | 70% → 84% | $0.0270 → $0.0298 | 2/3 | 0 |
| `news_ai_regulation` | 0% → 0% | 84% → 72% | $0.0262 → $0.0254 | 0/3 | 0 |
| `news_climate` | 0% → 0% | 77% → 76% | $0.0268 → $0.0290 | 1/3 | 0 |
| `news_semiconductors` | 0% → 0% | 79% → 73% | $0.0556 → $0.0561 | 1/3 | 1 |
| `postgres_vs_mysql` | 0% → 0% | 67% → 67% | $0.0275 → $0.0277 | 0/3 | 0 |
| `heat_pump_vs_furnace` | 0% → 0% | 67% → 74% | $0.0274 → $0.0271 | 0/3 | 0 |
| `lfp_vs_nmc` | 0% → 0% | 40% → 75% | $0.0559 → $0.0564 | 2/3 | 0 |
| `rust_vs_go` | 5% → 0% | 69% → 70% | $0.0275 → $0.0273 | 0/3 | 0 |
| `raft` | 0% → 0% | 70% → 71% | $0.0268 → $0.0272 | 0/3 | 0 |
| `crispr_editing` | 6% → 0% | 64% → 56% | $0.0267 → $0.0299 | 2/3 | 8 |
| `ambiguous_mercury` | 0% → 0% | 74% → 71% | $0.0269 → $0.0274 | 1/3 | 0 |
| `no_answer_math_nobel` | 7% → 0% | 76% → 76% | $0.0243 → $0.0264 | 2/3 | 1 |
| **Overall** | 2% → 0% | 69% → 72% | $0.0316 → $0.0328 | 12/45 | 10 |
<!-- compare:end -->

## Results

<!-- results:start -->
_Run 2026-10-23: 15 questions x 3 runs, generator `google/gemini-2.5-flash`, judge `openai/gpt-4.1-mini`, citation guard on, total spend $1.55. Raw data: `results/2026-10-23-guard-v2.json`._

| Question | Depth | Runs | Sources | Citation coverage | Invented sources | Domains cited | Supported / partial | Handling | Latency | Tokens | Cost / run |
|---|---|---|---|---|---|---|---|---|---|---|---|
| `apollo11` | quick | 3 | 6.0 | 80% | 0% | 4.7 | 93% / 0% | — | 18.6s | 4,609 | $0.0255 |
| `berlin_wall` | quick | 3 | 6.0 | 68% | 0% | 5.3 | 100% / 0% | — | 17.7s | 4,248 | $0.0252 |
| `penicillin` | standard | 3 | 14.7 | 86% | 0% | 10.3 | 100% / 0% | — | 34.9s | 10,117 | $0.0511 |
| `montreal_protocol` | quick | 3 | 6.0 | 84% | 0% | 5.3 | 93% / 7% | — | 27.9s | 8,039 | $0.0298 |
| `news_ai_regulation` | quick | 3 | 6.0 | 72% | 0% | 5.3 | 100% / 0% | — | 19.8s | 4,587 | $0.0254 |
| `news_climate` | quick | 3 | 6.0 | 76% | 0% | 5.3 | 100% / 0% | — | 25.6s | 7,063 | $0.0290 |
| `news_semiconductors` | standard | 3 | 16.0 | 73% | 0% | 9.3 | 100% / 0% | — | 45.9s | 14,188 | $0.0561 |
| `postgres_vs_mysql` | quick | 3 | 6.0 | 67% | 0% | 5.0 | 87% / 13% | — | 26.3s | 6,410 | $0.0277 |
| `heat_pump_vs_furnace` | quick | 3 | 6.0 | 74% | 0% | 5.7 | 100% / 0% | — | 25.0s | 5,732 | $0.0271 |
| `lfp_vs_nmc` | standard | 3 | 14.7 | 75% | 0% | 11.3 | 93% / 0% | — | 44.7s | 17,613 | $0.0564 |
| `rust_vs_go` | quick | 3 | 6.0 | 70% | 0% | 5.7 | 87% / 7% | — | 23.1s | 6,253 | $0.0273 |
| `raft` | quick | 3 | 6.0 | 71% | 0% | 4.3 | 100% / 0% | — | 21.2s | 5,504 | $0.0272 |
| `crispr_editing` | quick | 3 | 6.0 | 56% | 0% | 4.0 | 100% / 0% | — | 24.8s | 8,144 | $0.0299 |
| `ambiguous_mercury` | quick | 3 | 6.0 | 71% | 0% | 5.0 | 100% / 0% | notes ambiguity 3/3 | 23.1s | 6,113 | $0.0274 |
| `no_answer_math_nobel` | quick | 3 | 6.0 | 76% | 0% | 5.0 | 100% / 0% | flags no-answer 3/3 | 20.4s | 6,141 | $0.0264 |
| **Overall** |  | 45 | 7.8 | 72% | 0% | 6.1 | 97% / 2% | flags no-answer 3/3, notes ambiguity 3/3 | 26.6s | 7,651 | $0.0328 |

```
Runs: 45 (15 questions x 3), errors: 0
Citation coverage: 72%
Invented-source rate: 0% (0 URLs)
Citation support (judge, n=225): 97% supported, 2% partial, 1% unsupported
Sources / run: 7.8, unique domains cited / run: 6.1
Empty-result subtasks: 0/106
Latency / run: 26.6s, tokens / run: 7,651, cost / run: $0.0328
Total eval spend (incl. judge): $1.55
No-answer handling: 3/3 correct
Ambiguity acknowledged: 3/3
Citation guard: retried 12/45 runs, links stripped in 3 runs (10 links)
```
<!-- results:end -->
