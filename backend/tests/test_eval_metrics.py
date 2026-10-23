from evals import metrics, report


def result(url: str, summary: str = "summary") -> dict:
    return {"query": "q", "search_result": summary, "source": url, "publish_date": "", "title": ""}


REPORT = """\
# AI Chips

## Market
- Sales grew 20% in 2026 [Reuters](https://www.reuters.com/chips/?utm_source=x)
- Nvidia leads the market.

## Outlook
Demand stays strong [FT](https://ft.com/a#section). Supply is tight. See [Fake](https://made-up.example/b).
"""

RESULTS = [result("https://reuters.com/chips"), result("https://www.ft.com/a/"), result("https://other.com/x")]


def test_normalize_url_ignores_scheme_www_slash_fragment_and_utm():
    assert metrics.normalize_url("https://www.Reuters.com/chips/?utm_source=x&id=3#top") == "reuters.com/chips?id=3"
    assert metrics.normalize_url("http://reuters.com/chips") == metrics.normalize_url("https://www.reuters.com/chips/")


def test_report_units_skip_headings_and_split_prose():
    units = metrics.report_units(REPORT)
    assert units == [
        "Sales grew 20% in 2026 [Reuters](https://www.reuters.com/chips/?utm_source=x)",
        "Nvidia leads the market.",
        "Demand stays strong [FT](https://ft.com/a#section).",
        "Supply is tight.",
        "See [Fake](https://made-up.example/b).",
    ]


def test_score_run():
    m = metrics.score_run(REPORT, RESULTS + [result("")])
    assert m["sources_returned"] == 3
    assert m["citation_coverage"] == 3 / 5
    assert m["cited_urls"] == 3
    assert m["invented_urls"] == ["https://made-up.example/b"]
    assert m["invented_rate"] == 1 / 3
    assert m["unique_domains_returned"] == 3
    assert m["unique_domains_cited"] == 3


def test_score_run_without_citations():
    m = metrics.score_run("No results were found.", [])
    assert m["citation_coverage"] == 0
    assert m["invented_rate"] is None


def test_sample_claims_excludes_invented_and_is_deterministic():
    claims = metrics.sample_claims(REPORT, RESULTS, k=5, seed="x")
    assert [c["claim"] for c in claims] == ["Sales grew 20% in 2026 Reuters", "Demand stays strong FT."]
    assert claims[0]["sources"][0]["url"] == "https://reuters.com/chips"
    assert metrics.sample_claims(REPORT, RESULTS, k=1, seed="s") == metrics.sample_claims(REPORT, RESULTS, k=1, seed="s")


def test_summarize_pools_rates_across_runs():
    def run(qid, cited_units, units, invented, cited, supported, judged, handled=None):
        m = {
            "sources_returned": 6, "report_units": units, "cited_units": cited_units,
            "invented_urls": ["u"] * invented, "cited_urls": cited, "unique_domains_cited": 2,
            "unique_domains_returned": 3, "fallback_subtasks": 0, "subtasks": 2,
            "judged_claims": judged, "claims_supported": supported, "claims_partial": judged - supported,
            "claims_unsupported": 0,
        }
        if handled is not None:
            m["empty_handling_correct"] = handled
        return {
            "question_id": qid, "depth": "quick", "category": "c", "error": None, "metrics": m,
            "latency_s": {"total": 10.0}, "usage": {"planner": {"prompt_tokens": 100, "completion_tokens": 50}},
            "cost_usd": {"pipeline": 0.01, "judge": 0.001},
        }

    runs = [run("a", 4, 5, 0, 4, 4, 4), run("a", 1, 5, 1, 2, 1, 2, handled=False), run("b", 0, 2, 0, 0, 0, 0)]
    runs.append({"question_id": "b", "depth": "quick", "category": "c", "error": "boom", "cost_usd": {}})

    s = report.summarize(runs)
    a = s["rows"][0]
    assert a["coverage"] == 5 / 10
    assert a["invented"] == 1 / 6
    assert a["supported"] == 5 / 6
    assert a["empty_handling"] == (0, 1)
    assert s["overall"]["runs"] == 4 and s["overall"]["errors"] == 1
    assert s["overall"]["coverage"] == 5 / 12
    assert "**Overall**" in report.table(s)
    assert s["overall"]["first_draft_invented"] == 1 and s["overall"]["first_draft_invented_runs"] == 1


def test_citation_failures_lists_unknown_ids_and_closest_source_per_draft():
    from agents.citation_guard import number_sources
    from models.schemas import SearchResult

    sources = number_sources([SearchResult(**result("https://en.wikipedia.org/wiki/CRISPR")), SearchResult(**result("https://ft.com/a"))])
    drafts = [
        "- Claim [S1].\n- Claim [S7].\n- Claim [wiki](https://en.wikipedia.com/wiki/CRISPR).\n",
        "- Claim [S1].\n- Claim https://unrelated.example/zzz.\n",
    ]

    failures = metrics.citation_failures(drafts, sources)

    assert failures[0] == {"draft": "first", "kind": "id", "citation": "S7"}
    assert failures[1]["citation"] == "https://en.wikipedia.com/wiki/CRISPR"
    assert failures[1]["closest_source"] == "https://en.wikipedia.org/wiki/CRISPR"
    assert failures[1]["similarity"] > 0.9
    assert failures[2]["draft"] == "retry" and failures[2]["similarity"] < 0.6
    assert metrics.citation_failures(["- Clean [S2]."], sources) == []


def test_comparison_tables_have_one_column_per_config():
    def summary(coverage, unverified):
        overall = {"runs": 3, "coverage": coverage, "invented": 0.0, "invented_count": 0, "supported": 1.0,
                   "partial": 0.0, "judged": 5, "unverified": unverified, "latency": 20.0, "cost": 0.03,
                   "first_draft_invented": 1, "first_draft_invented_runs": 1}
        return {"rows": [{"id": "raft", **overall}], "overall": overall}

    configs = [("No guard", summary(0.5, 0)), ("Guard v2", summary(0.6, 2)), ("ID citations", summary(0.7, 0))]

    overall = report.comparison_table(configs)
    assert "| Metric | No guard | Guard v2 | ID citations |" in overall
    assert "| Citation coverage | 50% | 60% | 70% |" in overall
    assert "| Unverified claims (citation removed) | 0 | 2 | 0 |" in overall
    assert "| `raft` | 50% → 60% → 70% |" in report.question_comparison_table(configs)
