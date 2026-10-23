"""Pure scoring functions for eval runs. No network, no app imports."""

import random
import re
from urllib.parse import parse_qsl, urlencode, urlparse

LINK_RE = re.compile(r"\[([^\]]+)\]\((https?://[^)\s]+)\)")
_BULLET_RE = re.compile(r"^(?:[-*+]|\d+[.)])\s+")
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+(?=[A-Z\[\"(])")


def normalize_url(url: str) -> str:
    """Comparable form: no scheme, no www., no trailing slash, fragment or utm_* params."""
    parsed = urlparse(url.strip())
    host = parsed.netloc.lower().removeprefix("www.")
    path = parsed.path.rstrip("/")
    query = urlencode([(k, v) for k, v in parse_qsl(parsed.query) if not k.lower().startswith("utm_")])
    return host + path + (f"?{query}" if query else "")


def domain(url: str) -> str:
    return urlparse(url).netloc.lower().removeprefix("www.")


def report_units(markdown: str) -> list[str]:
    """Bullets count as one unit each; other prose is split into sentences.

    Headings, horizontal rules, table separators and blank lines are skipped.
    """
    units = []
    for raw in markdown.splitlines():
        line = raw.strip().lstrip(">").strip()
        if not line or line.startswith("#") or re.fullmatch(r"[-*_=|: ]{3,}", line):
            continue
        if _BULLET_RE.match(line):
            text = _BULLET_RE.sub("", line).strip()
            if text:
                units.append(text)
            continue
        units.extend(s for s in _SENTENCE_SPLIT_RE.split(line) if s.strip())
    return units


def is_cited(unit: str) -> bool:
    return bool(LINK_RE.search(unit))


def cited_urls(markdown: str) -> list[str]:
    """Unique cited URLs in order of first appearance."""
    seen, urls = set(), []
    for _, url in LINK_RE.findall(markdown):
        if url not in seen:
            seen.add(url)
            urls.append(url)
    return urls


def score_run(report: str, results: list[dict]) -> dict:
    """Deterministic metrics for one pipeline run.

    `results` are SearchResult dicts (query, search_result, source, publish_date, title).
    """
    returned = [r["source"] for r in results if r["source"]]
    returned_norm = {normalize_url(u) for u in returned}

    units = report_units(report)
    cited_units = [u for u in units if is_cited(u)]
    cited = cited_urls(report)
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
