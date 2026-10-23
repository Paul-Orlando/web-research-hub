"""Pure scoring functions for eval runs. No network.

Parsing reuses the citation guard (link pattern, visible-URL extraction, URL
normalization, report units), so the eval and the guard agree on what counts
as a citation and as an invented URL.
"""

import random
from urllib.parse import urlparse

from agents.citation_guard import LINK_RE, normalize_url, report_units, visible_urls  # noqa: F401 (re-exported)


def domain(url: str) -> str:
    return urlparse(url).netloc.lower().removeprefix("www.")


def is_cited(unit: str) -> bool:
    return bool(LINK_RE.search(unit))


def score_run(report: str, results: list[dict]) -> dict:
    """Deterministic metrics for one pipeline run.

    `results` are SearchResult dicts (query, search_result, source, publish_date, title).
    Coverage counts [text](url) citations only; invented URLs count every URL a
    reader can see (link targets, labels, bare URLs), since bare URLs render as links.
    """
    returned = [r["source"] for r in results if r["source"]]
    returned_norm = {normalize_url(u) for u in returned}

    units = report_units(report)
    cited_units = [u for u in units if is_cited(u)]
    cited = visible_urls(report)
    invented = [u for u in cited if normalize_url(u) not in returned_norm]

    return {
        "sources_returned": len(returned),
        "report_units": len(units),
        "cited_units": len(cited_units),
        "citation_coverage": len(cited_units) / len(units) if units else None,
        "cited_urls": len(cited),
        "invented_urls": invented,
        "invented_rate": len(invented) / len(cited) if cited else None,
        "unique_domains_returned": len({domain(u) for u in returned}),
        "unique_domains_cited": len({domain(u) for u in cited}),
        "unverified_claims": report.count("(unverified)"),
    }


def strip_links(text: str) -> str:
    return LINK_RE.sub(lambda m: m.group(1), text)


def sample_claims(report: str, results: list[dict], k: int, seed: str) -> list[dict]:
    """Up to k (claim, source summaries) pairs whose citations resolve to a search result.

    Claims citing only invented URLs are excluded; they're counted by score_run.
    """
    by_url: dict[str, list[dict]] = {}
    for r in results:
        if r["source"]:
            by_url.setdefault(normalize_url(r["source"]), []).append(r)

    candidates = []
    for unit in report_units(report):
        sources = [
            r
            for _, url in LINK_RE.findall(unit)
            for r in by_url.get(normalize_url(url), [])
        ]
        if sources:
            candidates.append({
                "claim": strip_links(unit),
                "sources": [{"url": r["source"], "summary": r["search_result"]} for r in sources],
            })

    rng = random.Random(seed)
    return rng.sample(candidates, k) if len(candidates) > k else candidates
