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
run it retries. The ID-citation run cost $1.42 (no retries).

| Flag | Default | |
|---|---|---|
| `--questions N` | all | only the first N questions in `questions.yaml` |
| `--only IDS` | all | comma-separated question ids, e.g. `--only raft,crispr_editing` |
| `--runs N` | 3 | runs per question |
| `--judge-model M` | `openai/gpt-4.1-mini` | OpenRouter model for the citation judge |
| `--max-cost USD` | 5.00 | stop once the estimated spend passes this |
| `--mcp-url URL` | `http://localhost:8001` | local MCP server |
| `--no-guard` | off | skip the citation guard: source IDs are still mapped to links, but there is no retry and no URL check |
| `--tag T` | none | write `results/<date>-<T>.json` instead of `results/<date>.json` |
| `--label L` | `ID citations` | this run's column name in the comparison table |
| `--compare-to LABEL=FILE ...` | none | earlier results files (relative to `evals/`), oldest first; writes the comparison table, using only the questions in this run |

Output: raw per-run data (plan, search results, numbered source list, the
summarizer's first and retry drafts, bad citations, final report, metrics,
judge labels, token usage) goes to `results/<date>.json`. The file is
rewritten after every run, so an interrupted eval keeps the runs it finished
(`meta.complete` is `false` until the end). The summary and comparison tables
below are rewritten when the eval finishes. A second run on the same day
overwrites both (use `--tag` to keep them apart).

Each run's `citation_failures` lists every unknown source ID and invented URL
in the first and retry drafts. Each invented URL comes with the most similar
returned URL (`closest_source`, `similarity`), to tell a mis-copied source
from one that isn't in the results at all.

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
| Citation coverage | % of report units (bullets, plus sentences of non-bullet prose; headings excluded) containing a `[text](url)` citation, scored after source IDs are mapped to links |
| Invented sources | % of unique visible URLs (link targets, URLs in link labels, and bare URLs, which the frontend renders as links) not among the run's search-result URLs, after normalizing scheme, `www.`, trailing slash, fragment and `utm_*`. URLs with balanced parentheses are parsed whole. **Target 0%.** The offending URLs are listed in the raw JSON |
| Invented in first draft | Unknown source IDs plus invented URLs in the summarizer's first draft, before the guard retries or strips anything (for runs without the guard, the report itself) |
| Unverified claims | `(unverified)` markers in the final report: citations the guard removed after its retry still pointed at no returned source |
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

## Citation guard and ID citations

Three configurations, 15 questions x 3 runs each. "Shown to reader" scores
the report the user actually sees.

- **No guard** (2026-10-22): the summarizer saw each source's URL and wrote
  `[source](url)` links itself.
- **Guard v2** (`f6168ba`, 2026-10-23): same prompt, plus a server-side check
  of every visible URL against the URLs the orchestrator returned. On a
  problem (an invented URL, zero citations, or coverage under 50%) it retried
  the summarizer once with a correction note, then removed anything still
  invented, leaving `(unverified)`.
- **ID citations** (2026-10-23): the summarizer gets a numbered source list
  (`[S1]` title, domain, date, summary) with **no URLs**, and cites
  `[S1]` or `[S1][S4]`. It is told to leave out any claim no listed source
  supports. The backend (`agents/citation_guard.py`) maps each ID to a
  `[domain](url)` link, so the frontend, exports and session history are
  unchanged. An unknown ID counts as invented: one retry, then it becomes
  `(unverified)`. Raw URLs in the model output are still checked as in guard
  v2, as a backstop.

**Why the change.** All 5 invented URLs in the no-guard run were near-copies
of real search results, not sources cited from memory. The model mis-copied
long URLs, so the links were broken or pointed at the wrong page:

| Question | Cited (invented) | Real search result |
|---|---|---|
| `berlin_wall` | AP News article ID `...0c1431c13fab4c52a5`**`5`**`139d7992f5530b` (extra digit) | `...0c1431c13fab4c52a5139d7992f5530b` |
| `montreal_protocol` | `diva-portal.org/.../diva2:`**`1381777`**`/FULLTEXT01.pdf` | `diva2:1381798` |
| `rust_vs_go` | `johal.in/language-benchmark-`**`benchmark-`**`rust-185-vs-go-123-vs` (doubled word) | `johal.in/language-benchmark-rust-185-vs-go-123-vs` |
| `crispr_editing` | `en.wikipedia.`**`com`**`/wiki/Prime_editing` | `en.wikipedia.org/wiki/Prime_editing` |
| `no_answer_math_nobel` | **`imu-news.org`**`/imu-news/archive/2025/...` | `mathunion.org/imu-news/archive/2025/...` |

In guard v2, `crispr_editing` run 0's first draft had **no** invented URLs
but low coverage. The low-coverage retry ("every factual claim must include a
citation") then produced 8 invented URLs, which the guard removed. That is why
`crispr_editing` coverage fell to 56%: pressure to cite more made the model
cite sources it didn't have. The removed URLs weren't saved, so they can't be
classified. Since ID citations, the coverage retry says "cite a source ID for
each claim, and remove claims no listed source supports". It never asks for
more citations without allowing removal, and every run saves its first and
retry drafts plus a list of bad citations (`citation_failures`).

**Result.** With ID citations, no first draft in 45 runs cited an unknown ID
or wrote a URL, so the guard never retried and removed nothing. Coverage rose
from 72% to 84%. Judge support was 99% (n=225), latency fell from 26.6 s to
19.5 s per query (no retries, shorter prompt), and cost fell 10%. A 5-question
technical subset (`crispr_editing`, `penicillin`, `lfp_vs_nmc`,
`heat_pump_vs_furnace`, `raft`) was run first as a go/no-go check:
`results/2026-10-23-ids-tech.json`.

Reports are 3% shorter on average than in guard v2 (29.7 vs 30.6 units per
run), but not evenly. `raft` (-24%, 28.3 vs 37.3 units) and
`heat_pump_vs_furnace` (-32%, 24.0 vs 35.3) were shorter in all three runs
and have slightly fewer cited claims in absolute terms (about 25 vs 27 and 24
vs 26). The "leave the claim out" rule seems to trim them, so part of their
coverage gain comes from dropping uncited text. Other questions grew, e.g.
`news_semiconductors` (+29%) and `montreal_protocol` (+31%).
`crispr_editing`'s judge support was 87% (13 of 15 sampled claims), against
100% in guard v2.

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
_15 questions, 45 runs per configuration; search results differ between runs. No guard: `results/2026-10-22.json`; Guard v2: `results/2026-10-23-guard-v2.json`; ID citations: `results/2026-10-23-ids.json`._

| Metric | No guard | Guard v2 | ID citations |
|---|---|---|---|
| Invented sources shown to reader | 2% (5) | 0% (0) | 0% (0) |
| Invented citations in first draft | 5 in 5 runs | 7 in 6 runs | 0 in 0 runs |
| Citation coverage | 69% | 72% | 84% |
| Report units / run | 32.6 | 30.6 | 29.7 |
| Judge: supported / partial | 97% / 3% (n=220) | 97% / 2% (n=225) | 99% / 0% (n=225) |
| Unverified claims (citation removed) | 0 | 10 | 0 |
| Guard retries | — | 12/45 | 0/45 |
| Latency / run | 25.8s | 26.6s | 19.5s |
| Cost / run | $0.0316 | $0.0328 | $0.0294 |

Per question (No guard → Guard v2 → ID citations):

| Question | Citation coverage | Report units | Supported | Unverified | Guard retried | Cost / run |
|---|---|---|---|---|---|---|
| `apollo11` | 80% → 80% → 94% | 20.0 → 25.3 → 16.7 | 100% → 93% → 100% | 0 → 0 → 0 | — → 0/3 → 0/3 | $0.0251 → $0.0255 → $0.0237 |
| `berlin_wall` | 59% → 68% → 85% | 27.7 → 25.0 → 22.7 | 93% → 100% → 100% | 0 → 0 → 0 | — → 0/3 → 0/3 | $0.0257 → $0.0252 → $0.0235 |
| `penicillin` | 85% → 86% → 95% | 22.0 → 18.7 → 20.0 | 93% → 100% → 100% | 0 → 0 → 0 | — → 1/3 → 0/3 | $0.0441 → $0.0511 → $0.0458 |
| `montreal_protocol` | 70% → 84% → 89% | 36.7 → 16.3 → 21.3 | 100% → 93% → 100% | 0 → 0 → 0 | — → 2/3 → 0/3 | $0.0270 → $0.0298 → $0.0244 |
| `news_ai_regulation` | 84% → 72% → 94% | 26.3 → 24.0 → 17.3 | 100% → 100% → 100% | 0 → 0 → 0 | — → 0/3 → 0/3 | $0.0262 → $0.0254 → $0.0239 |
| `news_climate` | 77% → 76% → 89% | 28.7 → 32.0 → 18.0 | 100% → 100% → 100% | 0 → 0 → 0 | — → 1/3 → 0/3 | $0.0268 → $0.0290 → $0.0243 |
| `news_semiconductors` | 79% → 73% → 89% | 35.7 → 40.0 → 51.7 | 100% → 100% → 100% | 0 → 1 → 0 | — → 1/3 → 0/3 | $0.0556 → $0.0561 → $0.0531 |
| `postgres_vs_mysql` | 67% → 67% → 74% | 43.7 → 42.0 → 44.7 | 100% → 87% → 100% | 0 → 0 → 0 | — → 0/3 → 0/3 | $0.0275 → $0.0277 → $0.0255 |
| `heat_pump_vs_furnace` | 67% → 74% → 99% | 42.3 → 35.3 → 24.0 | 100% → 100% → 100% | 0 → 0 → 0 | — → 0/3 → 0/3 | $0.0274 → $0.0271 → $0.0244 |
| `lfp_vs_nmc` | 40% → 75% → 78% | 50.7 → 38.0 → 38.7 | 100% → 93% → 100% | 0 → 0 → 0 | — → 2/3 → 0/3 | $0.0559 → $0.0564 → $0.0515 |
| `rust_vs_go` | 69% → 70% → 80% | 42.3 → 39.0 → 44.7 | 100% → 87% → 100% | 0 → 0 → 0 | — → 0/3 → 0/3 | $0.0275 → $0.0273 → $0.0255 |
| `raft` | 70% → 71% → 87% | 31.0 → 37.3 → 28.3 | 87% → 100% → 100% | 0 → 0 → 0 | — → 0/3 → 0/3 | $0.0268 → $0.0272 → $0.0234 |
| `crispr_editing` | 64% → 56% → 80% | 30.3 → 36.7 → 35.0 | 93% → 100% → 87% | 0 → 8 → 0 | — → 2/3 → 0/3 | $0.0267 → $0.0299 → $0.0244 |
| `ambiguous_mercury` | 74% → 71% → 82% | 35.0 → 32.7 → 41.0 | 100% → 100% → 100% | 0 → 0 → 0 | — → 1/3 → 0/3 | $0.0269 → $0.0274 → $0.0250 |
| `no_answer_math_nobel` | 76% → 76% → 75% | 16.7 → 16.7 → 21.3 | 87% → 100% → 100% | 0 → 1 → 0 | — → 2/3 → 0/3 | $0.0243 → $0.0264 → $0.0232 |
<!-- compare:end -->

## Results

<!-- results:start -->
_Run 2026-10-23: 15 questions x 3 runs, generator `google/gemini-2.5-flash`, judge `openai/gpt-4.1-mini`, citation guard on, source-ID citations, total spend $1.42. Raw data: `results/2026-10-23-ids.json`._

| Question | Depth | Runs | Sources | Citation coverage | Invented sources | Domains cited | Supported / partial | Handling | Latency | Tokens | Cost / run |
|---|---|---|---|---|---|---|---|---|---|---|---|
| `apollo11` | quick | 3 | 6.0 | 94% | 0% | 5.7 | 100% / 0% | — | 15.6s | 3,832 | $0.0237 |
| `berlin_wall` | quick | 3 | 6.0 | 85% | 0% | 4.7 | 100% / 0% | — | 16.3s | 3,391 | $0.0235 |
| `penicillin` | standard | 3 | 14.7 | 95% | 0% | 10.0 | 100% / 0% | — | 21.2s | 6,243 | $0.0458 |
| `montreal_protocol` | quick | 3 | 6.0 | 89% | 0% | 4.0 | 100% / 0% | — | 16.7s | 4,476 | $0.0244 |
| `news_ai_regulation` | quick | 3 | 6.0 | 94% | 0% | 3.3 | 100% / 0% | — | 17.3s | 3,925 | $0.0239 |
| `news_climate` | quick | 3 | 6.0 | 89% | 0% | 5.0 | 100% / 0% | — | 16.6s | 4,073 | $0.0243 |
| `news_semiconductors` | standard | 3 | 16.0 | 89% | 0% | 13.7 | 100% / 0% | — | 34.8s | 9,697 | $0.0531 |
| `postgres_vs_mysql` | quick | 3 | 6.0 | 74% | 0% | 5.3 | 100% / 0% | — | 20.4s | 5,638 | $0.0255 |
| `heat_pump_vs_furnace` | quick | 3 | 6.0 | 99% | 0% | 5.0 | 100% / 0% | — | 17.6s | 4,609 | $0.0244 |
| `lfp_vs_nmc` | standard | 3 | 16.0 | 78% | 0% | 11.3 | 100% / 0% | — | 30.9s | 9,412 | $0.0515 |
| `rust_vs_go` | quick | 3 | 6.0 | 80% | 0% | 5.3 | 100% / 0% | — | 19.5s | 5,376 | $0.0255 |
| `raft` | quick | 3 | 6.0 | 87% | 0% | 3.7 | 100% / 0% | — | 13.1s | 3,871 | $0.0234 |
| `crispr_editing` | quick | 3 | 6.0 | 80% | 0% | 4.0 | 87% / 7% | — | 18.6s | 4,489 | $0.0244 |
| `ambiguous_mercury` | quick | 3 | 6.0 | 82% | 0% | 4.3 | 100% / 0% | notes ambiguity 3/3 | 19.0s | 4,409 | $0.0250 |
| `no_answer_math_nobel` | quick | 3 | 6.0 | 75% | 0% | 4.0 | 100% / 0% | flags no-answer 3/3 | 15.2s | 3,550 | $0.0232 |
| **Overall** |  | 45 | 7.9 | 84% | 0% | 6.0 | 99% / 0% | flags no-answer 3/3, notes ambiguity 3/3 | 19.5s | 5,133 | $0.0294 |

```
Runs: 45 (15 questions x 3), errors: 0
Citation coverage: 84%
Invented-source rate: 0% (0 URLs)
Citation support (judge, n=225): 99% supported, 0% partial, 0% unsupported
Sources / run: 7.9, unique domains cited / run: 6.0
Empty-result subtasks: 0/107
Latency / run: 19.5s, tokens / run: 5,133, cost / run: $0.0294
Total eval spend (incl. judge): $1.42
No-answer handling: 3/3 correct
Ambiguity acknowledged: 3/3
Unverified claims (citation removed): 0
Citation guard: retried 0/45 runs, links stripped in 0 runs (0 links)
```
<!-- results:end -->
