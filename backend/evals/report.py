"""Aggregates run records into per-question and overall tables."""

import re
from pathlib import Path
from statistics import mean

START, END = "<!-- results:start -->", "<!-- results:end -->"
CMP_START, CMP_END = "<!-- compare:start -->", "<!-- compare:end -->"


def pct(x) -> str:
    return "—" if x is None else f"{x * 100:.0f}%"


def _ratio(num: int, den: int):
    return num / den if den else None


def _aggregate(runs: list[dict]) -> dict:
    ok = [r for r in runs if not r["error"]]
    ms = [r["metrics"] for r in ok]
    agg = {"runs": len(runs), "errors": len(runs) - len(ok)}
    if not ok:
        return agg
    judged = sum(m["judged_claims"] for m in ms)
    agg.update({
        "sources": mean(m["sources_returned"] for m in ms),
        "coverage": _ratio(sum(m["cited_units"] for m in ms), sum(m["report_units"] for m in ms)),
        "invented": _ratio(sum(len(m["invented_urls"]) for m in ms), sum(m["cited_urls"] for m in ms)),
        "invented_count": sum(len(m["invented_urls"]) for m in ms),
        "domains_cited": mean(m["unique_domains_cited"] for m in ms),
        "domains_returned": mean(m["unique_domains_returned"] for m in ms),
        "fallback_subtasks": sum(m["fallback_subtasks"] for m in ms),
        "subtasks": sum(m["subtasks"] for m in ms),
        "judged": judged,
        "supported": _ratio(sum(m["claims_supported"] for m in ms), judged),
        "partial": _ratio(sum(m["claims_partial"] for m in ms), judged),
        "unsupported": _ratio(sum(m["claims_unsupported"] for m in ms), judged),
        "latency": mean(r["latency_s"]["total"] for r in ok),
        "tokens": mean(
            sum(u["prompt_tokens"] + u["completion_tokens"] for s, u in r["usage"].items() if s != "judge")
            for r in ok
        ),
        "cost": mean(r["cost_usd"]["pipeline"] for r in ok),
    })
    handled = [m["empty_handling_correct"] for m in ms if "empty_handling_correct" in m]
    if handled:
        agg["empty_handling"] = (sum(handled), len(handled))
    ambiguity = [m["acknowledges_ambiguity"] for m in ms if "acknowledges_ambiguity" in m]
    if ambiguity:
        agg["ambiguity"] = (sum(ambiguity), len(ambiguity))
    guarded = [m["guard"] for m in ms if "guard" in m]
    if guarded:
        agg["guard_retried"] = (sum(g["retried"] for g in guarded), len(guarded))
        agg["guard_stripped_runs"] = sum(1 for g in guarded if g["removed"])
        agg["guard_removed"] = sum(g["removed"] for g in guarded)
    return agg


def summarize(runs: list[dict]) -> dict:
    by_q: dict[str, list[dict]] = {}
    for r in runs:
        by_q.setdefault(r["question_id"], []).append(r)
    rows = []
    for qid, q_runs in by_q.items():
        rows.append({"id": qid, "depth": q_runs[0]["depth"], "category": q_runs[0]["category"], **_aggregate(q_runs)})
    return {"rows": rows, "overall": _aggregate(runs)}


def _handling(a: dict) -> str:
    parts = []
    if "empty_handling" in a:
        parts.append("flags no-answer {}/{}".format(*a["empty_handling"]))
    if "ambiguity" in a:
        parts.append("notes ambiguity {}/{}".format(*a["ambiguity"]))
    return ", ".join(parts) or "—"


def _row(label: str, depth: str, a: dict) -> str:
    if "sources" not in a:
        return f"| {label} | {depth} | {a['runs']} (all errored) |" + " — |" * 9
    errors = f" ({a['errors']} err)" if a["errors"] else ""
    return (
        f"| {label} | {depth} | {a['runs']}{errors} | {a['sources']:.1f} | {pct(a['coverage'])} | "
        f"{pct(a['invented'])} | {a['domains_cited']:.1f} | {pct(a['supported'])} / {pct(a['partial'])} | "
        f"{_handling(a)} | {a['latency']:.1f}s | {a['tokens']:,.0f} | ${a['cost']:.4f} |"
    )


def table(summary: dict) -> str:
    lines = [
        "| Question | Depth | Runs | Sources | Citation coverage | Invented sources | Domains cited "
        "| Supported / partial | Handling | Latency | Tokens | Cost / run |",
        "|---|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    lines += [_row(f"`{r['id']}`", r["depth"], r) for r in summary["rows"]]
    lines.append(_row("**Overall**", "", summary["overall"]))
    return "\n".join(lines)


def headline(meta: dict, summary: dict) -> str:
    o = summary["overall"]
    if "sources" not in o:
        return "All runs errored; no headline numbers."
    lines = [
        f"Runs: {o['runs']} ({meta['questions']} questions x {meta['runs_per_question']}), errors: {o['errors']}",
        f"Citation coverage: {pct(o['coverage'])}",
        f"Invented-source rate: {pct(o['invented'])} ({o['invented_count']} URLs)",
        f"Citation support (judge, n={o['judged']}): {pct(o['supported'])} supported, "
        f"{pct(o['partial'])} partial, {pct(o['unsupported'])} unsupported",
        f"Sources / run: {o['sources']:.1f}, unique domains cited / run: {o['domains_cited']:.1f}",
        f"Empty-result subtasks: {o['fallback_subtasks']}/{o['subtasks']}",
        f"Latency / run: {o['latency']:.1f}s, tokens / run: {o['tokens']:,.0f}, cost / run: ${o['cost']:.4f}",
        f"Total eval spend (incl. judge): ${meta['total_cost_usd']:.2f}",
    ]
    if "empty_handling" in o:
        lines.append("No-answer handling: {}/{} correct".format(*o["empty_handling"]))
    if "ambiguity" in o:
        lines.append("Ambiguity acknowledged: {}/{}".format(*o["ambiguity"]))
    if "guard_retried" in o:
        lines.append(
            "Citation guard: retried {}/{} runs, links stripped in {} runs ({} links)".format(
                *o["guard_retried"], o["guard_stripped_runs"], o["guard_removed"]
            )
        )
    return "\n".join(lines)


def _arrow(before, after, fmt) -> str:
    return f"{fmt(before)} → {fmt(after)}"


def _money(x) -> str:
    return "—" if x is None else f"${x:.4f}"


def comparison_table(before: dict, after: dict) -> str:
    before_rows = {r["id"]: r for r in before["rows"]}
    lines = [
        "| Question | Invented sources | Citation coverage | Cost / run | Guard retried | Links stripped |",
        "|---|---|---|---|---|---|",
    ]

    def row(label, b, a):
        retried = "{}/{}".format(*a["guard_retried"]) if "guard_retried" in a else "—"
        return (
            f"| {label} | {_arrow(b.get('invented'), a.get('invented'), pct)} "
            f"| {_arrow(b.get('coverage'), a.get('coverage'), pct)} "
            f"| {_arrow(b.get('cost'), a.get('cost'), _money)} | {retried} | {a.get('guard_removed', '—')} |"
        )

    for a in after["rows"]:
        lines.append(row(f"`{a['id']}`", before_rows.get(a["id"], {}), a))
    lines.append(row("**Overall**", before["overall"], after["overall"]))
    return "\n".join(lines)


def write_comparison(path: Path, before_meta: dict, before: dict, after_meta: dict, after: dict):
    b, a = before["overall"], after["overall"]
    block = (
        f"{CMP_START}\n"
        f"_Before: `{before_meta['results_file']}` (no guard, {b['runs']} runs). "
        f"After: `{after_meta['results_file']}` (citation guard on, {a['runs']} runs). "
        f"Same questions, 3 runs each; search results differ between runs._\n\n"
        f"{comparison_table(before, after)}\n"
        f"{CMP_END}"
    )
    text = path.read_text(encoding="utf-8")
    pattern = re.compile(re.escape(CMP_START) + r".*?" + re.escape(CMP_END), re.DOTALL)
    if not pattern.search(text):
        raise ValueError(f"{path} has no {CMP_START} / {CMP_END} markers")
    path.write_text(pattern.sub(lambda _: block, text), encoding="utf-8")


def write_readme(path: Path, meta: dict, summary: dict):
    results_file = meta.get("results_file", f"results/{meta['date']}.json")
    block = (
        f"{START}\n"
        f"_Run {meta['date']}: {meta['questions']} questions x {meta['runs_per_question']} runs, "
        f"generator `{meta['generator_model']}`, judge `{meta['judge_model']}`, "
        f"citation guard {'on' if meta.get('citation_guard') else 'off'}, "
        f"total spend ${meta['total_cost_usd']:.2f}"
        f"{' (stopped early at --max-cost)' if meta['stopped_early'] else ''}. "
        f"Raw data: `{results_file}`._\n\n"
        f"{table(summary)}\n\n"
        f"```\n{headline(meta, summary)}\n```\n"
        f"{END}"
    )
    text = path.read_text(encoding="utf-8")
    pattern = re.compile(re.escape(START) + r".*?" + re.escape(END), re.DOTALL)
    path.write_text(pattern.sub(lambda _: block, text), encoding="utf-8")
