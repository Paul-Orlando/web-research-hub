"""Research quality eval. Run from backend/:

    python -m evals.run [--questions N] [--runs N] [--judge-model M] [--max-cost USD]

Calls the pipeline in-process (planner -> orchestrator -> summarizer) against a
LOCAL MCP server. See evals/README.md for setup.
"""

import argparse
import asyncio
import json
import os
import sys
import time
from collections import defaultdict
from datetime import date, datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

import httpx
import yaml
from dotenv import load_dotenv

from evals import judge, metrics, report

BACKEND_DIR = Path(__file__).resolve().parent.parent
EVALS_DIR = Path(__file__).resolve().parent
LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1"}

# Exa pricing (exa.ai/pricing, checked 2026-10-22). The MCP server sends no
# search `type`, so Exa uses `auto`; summaries are billed per returned page.
EXA_SEARCH_USD = 7 / 1000
EXA_SUMMARY_PAGE_USD = 1 / 1000
SUPPORT_SAMPLE = 5


class UsageRecorder:
    """Wraps httpx.AsyncClient.send in this process to capture OpenRouter usage.

    The app's agents discard the `usage` block; this records it without
    changing app code. `stage` is set by the runner before each LLM call.
    """

    def __init__(self, prices: dict[str, tuple[float, float]]):
        self.prices = prices
        self.stage = "unknown"
        self.usage: dict[str, dict] = {}

    def reset(self):
        self.usage = defaultdict(lambda: {"prompt_tokens": 0, "completion_tokens": 0, "cost": 0.0, "calls": 0})

    def install(self):
        original = httpx.AsyncClient.send
        recorder = self

        async def send(client, request, *args, **kwargs):
            response = await original(client, request, *args, **kwargs)
            if request.url.host == "openrouter.ai" and request.url.path.endswith("/chat/completions"):
                recorder._record(request, response)
            return response

        httpx.AsyncClient.send = send

    def _record(self, request: httpx.Request, response: httpx.Response):
        try:
            model = json.loads(request.content)["model"]
            usage = response.json().get("usage") or {}
        except Exception:
            return
        prompt = usage.get("prompt_tokens", 0)
        completion = usage.get("completion_tokens", 0)
        cost = usage.get("cost")
        if cost is None:
            in_price, out_price = self.prices.get(model, (0.0, 0.0))
            cost = prompt * in_price + completion * out_price
        u = self.usage[self.stage]
        u["prompt_tokens"] += prompt
        u["completion_tokens"] += completion
        u["cost"] += cost
        u["calls"] += 1


def fetch_prices() -> dict[str, tuple[float, float]]:
    data = httpx.get("https://openrouter.ai/api/v1/models", timeout=30).json()["data"]
    return {m["id"]: (float(m["pricing"]["prompt"]), float(m["pricing"]["completion"])) for m in data}


def configure_env(mcp_url: str):
    load_dotenv(BACKEND_DIR / ".env", encoding="utf-8-sig")
    host = urlparse(mcp_url).hostname
    if host not in LOCAL_HOSTS:
        sys.exit(f"Refusing to run against {mcp_url}: evals must use a local MCP server (see evals/README.md).")
    # Forced (not setdefault): backend/.env points at the deployed server.
    # Must happen before tools.exa_search is imported; it reads env at import.
    os.environ["MCP_SERVER_URL"] = mcp_url
    for key in ("OPENROUTER_API_KEY", "MCP_API_KEY"):
        if not os.getenv(key):
            sys.exit(f"{key} is not set. Add it to backend/.env (see evals/README.md).")
    try:
        httpx.get(f"{mcp_url}/health", timeout=5).raise_for_status()
    except Exception as exc:
        sys.exit(f"Local MCP server not reachable at {mcp_url}/health ({exc}). Start it first.")


async def search_works() -> bool:
    """One real search through MCP -> Exa. exa_search swallows errors (dead
    Exa key, MCP 401) into its fallback entry, so a fallback here means broken."""
    from tools.exa_search import exa_search

    results = await exa_search("Apollo 11 moon landing", None, None, num_results=1)
    return any(r["source"] for r in results)


async def run_once(q: dict, run_idx: int, recorder: UsageRecorder, judge_model: str) -> dict:
    from agents.orchestrator import run_subtask
    from agents.planner import run_planner
    from agents.summarizer import run_summarizer
    from models.schemas import DepthMode
    from tools.exa_search import _FALLBACK

    fallback_text = _FALLBACK("")["search_result"]
    depth = DepthMode(q["depth"])
    record = {
        "question_id": q["id"],
        "question": q["question"],
        "category": q["category"],
        "depth": q["depth"],
        "expect": q.get("expect"),
        "run": run_idx,
        "error": None,
    }
    recorder.reset()

    # Mirrors main.py's /research event_stream, minus SSE and session history.
    try:
        t0 = time.perf_counter()
        recorder.stage = "planner"
        plan = await run_planner(q["question"], depth, [])
        t1 = time.perf_counter()

        all_results, fallback_subtasks, returned_pages = [], 0, 0
        for subtask in plan.subtasks:
            results = await run_subtask(subtask, depth)
            all_results.extend(results)
            real = [r for r in results if r.source]
            returned_pages += len(real)
            if not real and all(r.search_result == fallback_text for r in results):
                fallback_subtasks += 1
        t2 = time.perf_counter()

        recorder.stage = "summarizer"
        report_md = await run_summarizer(all_results, q["question"], [])
        t3 = time.perf_counter()
    except Exception as exc:
        record["error"] = f"{type(exc).__name__}: {exc}"
        record["usage"] = dict(recorder.usage)
        record["cost_usd"] = {"pipeline": sum(u["cost"] for u in recorder.usage.values()), "judge": 0.0}
        return record

    results_dicts = [r.model_dump() for r in all_results]
    m = metrics.score_run(report_md, results_dicts)
    m["subtasks"] = len(plan.subtasks)
    m["fallback_subtasks"] = fallback_subtasks
    m["all_fallback"] = fallback_subtasks == len(plan.subtasks)

    recorder.stage = "judge"
    judged = {"claims": [], "no_answer": None, "ambiguity": None, "error": None}
    try:
        claims = metrics.sample_claims(report_md, results_dicts, SUPPORT_SAMPLE, seed=f"{q['id']}:{run_idx}")
        judged["claims"] = await judge.judge_support(judge_model, claims)
        if q.get("expect") == "no_answer" or m["all_fallback"]:
            judged["no_answer"] = await judge.judge_no_answer(judge_model, q["question"], report_md)
        if q.get("expect") == "ambiguous":
            judged["ambiguity"] = await judge.judge_ambiguity(judge_model, q["question"], report_md)
    except Exception as exc:
        judged["error"] = f"{type(exc).__name__}: {exc}"

    labels = [c["label"] for c in judged["claims"]]
    m["judged_claims"] = sum(1 for lbl in labels if lbl != "unlabelled")
    for lbl in ("supported", "partial", "unsupported"):
        m[f"claims_{lbl}"] = labels.count(lbl)
    if judged["no_answer"] is not None:
        m["empty_handling_correct"] = bool(judged["no_answer"].get("flags_missing_info")) and not m["invented_urls"]
    if judged["ambiguity"] is not None:
        m["acknowledges_ambiguity"] = bool(judged["ambiguity"].get("acknowledges_ambiguity"))

    usage = dict(recorder.usage)
    llm_cost = sum(u["cost"] for stage, u in usage.items() if stage != "judge")
    exa_cost = len(plan.subtasks) * EXA_SEARCH_USD + returned_pages * EXA_SUMMARY_PAGE_USD
    record.update({
        "subtasks": [s.model_dump() for s in plan.subtasks],
        "results": results_dicts,
        "report": report_md,
        "latency_s": {
            "planner": round(t1 - t0, 2),
            "search": round(t2 - t1, 2),
            "summarizer": round(t3 - t2, 2),
            "total": round(t3 - t0, 2),
        },
        "usage": usage,
        "cost_usd": {
            "llm": llm_cost,
            "exa": exa_cost,
            "pipeline": llm_cost + exa_cost,
            "judge": usage.get("judge", {}).get("cost", 0.0),
        },
        "metrics": m,
        "judge": judged,
    })
    return record


async def main_async(args):
    from agents.planner import MODEL as GENERATOR_MODEL

    questions = yaml.safe_load((EVALS_DIR / "questions.yaml").read_text(encoding="utf-8"))
    if args.questions:
        questions = questions[: args.questions]

    recorder = UsageRecorder(fetch_prices())
    recorder.install()

    if not await search_works():
        sys.exit("Search check failed: the local MCP server returned no results (check EXA_API_KEY / MCP_API_KEY "
                 "in the server log).")
    print("Search check passed.", flush=True)

    started = datetime.now(timezone.utc)
    runs, spent, stopped_early = [], 0.0, False
    total = len(questions) * args.runs
    for q in questions:
        for i in range(args.runs):
            rec = await run_once(q, i, recorder, args.judge_model)
            runs.append(rec)
            spent += rec["cost_usd"]["pipeline"] + rec["cost_usd"]["judge"]
            m = rec.get("metrics", {})
            status = rec["error"] or (
                f"sources={m['sources_returned']} cov={report.pct(m['citation_coverage'])} "
                f"invented={report.pct(m['invented_rate'])} {rec['latency_s']['total']}s"
            )
            print(f"[{len(runs)}/{total}] {q['id']} run {i + 1}: {status}  (spent ${spent:.3f})", flush=True)
            if spent > args.max_cost:
                print(f"Stopping: spend ${spent:.2f} exceeded --max-cost ${args.max_cost:.2f}", flush=True)
                stopped_early = True
                break
            if m.get("all_fallback") and not await search_works():
                print("Stopping: search stopped working mid-run (every subtask fell back and the search check "
                      "failed). Results so far are saved.", flush=True)
                stopped_early = True
                break
        if stopped_early:
            break

    meta = {
        "date": date.today().isoformat(),
        "started_at": started.isoformat(),
        "finished_at": datetime.now(timezone.utc).isoformat(),
        "questions": len(questions),
        "runs_per_question": args.runs,
        "judge_model": args.judge_model,
        "generator_model": GENERATOR_MODEL,
        "mcp_server_url": os.environ["MCP_SERVER_URL"],
        "total_cost_usd": spent,
        "stopped_early": stopped_early,
    }
    out = EVALS_DIR / "results" / f"{meta['date']}.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps({"meta": meta, "runs": runs}, indent=2), encoding="utf-8")

    summary = report.summarize(runs)
    report.write_readme(EVALS_DIR / "README.md", meta, summary)
    print(f"\nRaw results: {out}\nSummary table written to {EVALS_DIR / 'README.md'}")
    print(report.headline(meta, summary))


def main():
    parser = argparse.ArgumentParser(description="Research quality evaluation")
    parser.add_argument("--questions", type=int, default=0, help="only the first N questions (default: all)")
    parser.add_argument("--runs", type=int, default=3, help="runs per question (default: 3)")
    parser.add_argument("--judge-model", default="openai/gpt-4.1-mini", help="OpenRouter model id for the judge")
    parser.add_argument("--max-cost", type=float, default=5.0, help="stop once estimated spend exceeds this (USD)")
    parser.add_argument("--mcp-url", default="http://localhost:8001", help="local MCP server URL")
    args = parser.parse_args()

    configure_env(args.mcp_url)
    asyncio.run(main_async(args))


if __name__ == "__main__":
    main()
