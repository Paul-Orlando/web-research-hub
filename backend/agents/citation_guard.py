import re
from typing import Awaitable, Callable
from urllib.parse import parse_qsl, urlencode, urlparse

from models.schemas import SearchResult

# URLs may contain one level of balanced parentheses, e.g. .../S0968-0004(20)30150-X
LINK_RE = re.compile(r"\[([^\]]+)\]\((https?://(?:[^()\s]|\([^()\s]*\))+)\)")
_BARE_URL_RE = re.compile(r"https?://[^\s<>\[\]\"'`]+")
_BULLET_RE = re.compile(r"^(?:[-*+]|\d+[.)])\s+")
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+(?=[A-Z\[\"(])")
# Source-ID citations: [S1], [S1, S4], and adjacent runs like [S1][S4]. A run
# followed by "(" is a markdown link label, not an ID citation.
_ID_TOKEN = r"\[S\d+(?:\s*[,;]\s*S\d+)*\]"
_ID_RUN_RE = re.compile(rf"{_ID_TOKEN}(?:\s*{_ID_TOKEN})*(?!\()")
_ID_RE = re.compile(r"S\d+")
MIN_COVERAGE = 0.5

Summarize = Callable[..., Awaitable[str]]


def normalize_url(url: str) -> str:
    """Comparable form: no scheme, no www., no trailing slash, fragment or utm_* params."""
    parsed = urlparse(url.strip())
    host = parsed.netloc.lower().removeprefix("www.")
    path = parsed.path.rstrip("/")
    query = urlencode([(k, v) for k, v in parse_qsl(parsed.query) if not k.lower().startswith("utm_")])
    return host + path + (f"?{query}" if query else "")


def source_domain(url: str) -> str:
    return urlparse(url).netloc.lower().removeprefix("www.")


def number_sources(results: list[SearchResult]) -> dict[str, list[SearchResult]]:
    """Source IDs S1, S2, ... in order of first appearance.

    Results without a URL (search fallbacks) get no ID; results sharing a URL
    share one ID. The summarizer prompt and the guard both use this numbering.
    """
    by_url: dict[str, list[SearchResult]] = {}
    for r in results:
        if r.source:
            by_url.setdefault(normalize_url(r.source), []).append(r)
    return {f"S{i}": group for i, group in enumerate(by_url.values(), 1)}


def cited_ids(markdown: str) -> list[str]:
    """Unique source IDs cited, in order of first appearance."""
    return list(dict.fromkeys(i for run in _ID_RUN_RE.findall(markdown) for i in _ID_RE.findall(run)))


def find_invalid_ids(markdown: str, sources: dict[str, list[SearchResult]]) -> list[str]:
    return [i for i in cited_ids(markdown) if i not in sources]


def resolve_ids(markdown: str, sources: dict[str, list[SearchResult]]) -> tuple[str, int]:
    """Replace source-ID citations with [domain](url) links. Returns (markdown, unknown IDs removed).

    An unknown ID becomes '(unverified)', once per citation run.
    """
    removed = 0

    def replace(m: re.Match) -> str:
        nonlocal removed
        parts = []
        for source_id in dict.fromkeys(_ID_RE.findall(m.group(0))):
            if source_id in sources:
                url = sources[source_id][0].source
                parts.append(f"[{source_domain(url)}]({url})")
            else:
                removed += 1
                if "(unverified)" not in parts:
                    parts.append("(unverified)")
        return " ".join(parts)

    return _ID_RUN_RE.sub(replace, markdown), removed


def cited_urls(markdown: str) -> list[str]:
    """Unique cited URLs in order of first appearance."""
    return list(dict.fromkeys(url for _, url in LINK_RE.findall(markdown)))


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


def citation_coverage(markdown: str) -> float:
    """Fraction of report units containing a citation (0.0 for an empty report)."""
    units = report_units(markdown)
    return sum(1 for u in units if LINK_RE.search(u)) / len(units) if units else 0.0


def _clean_bare(url: str) -> str:
    """Trim trailing punctuation and an unbalanced closing paren from a bare URL match."""
    url = url.rstrip(".,;:!?")
    while url.endswith(")") and url.count(")") > url.count("("):
        url = url[:-1].rstrip(".,;:!?")
    return url


def _bare_urls(text: str) -> list[str]:
    return [_clean_bare(u) for u in _BARE_URL_RE.findall(text)]


def visible_urls(markdown: str) -> list[str]:
    """Every URL a reader can see or click: link targets, URLs in link labels, and bare URLs.

    The frontend renders bare URLs as links, so they need checking too.
    """
    urls = [url for _, url in LINK_RE.findall(markdown)]
    urls += [u for label, _ in LINK_RE.findall(markdown) for u in _bare_urls(label)]
    urls += _bare_urls(LINK_RE.sub(" ", markdown))
    return list(dict.fromkeys(urls))


def find_invented(markdown: str, allowed: set[str]) -> list[str]:
    """Visible URLs whose normalized form isn't in `allowed` (already normalized)."""
    return [url for url in visible_urls(markdown) if normalize_url(url) not in allowed]


def strip_invented(markdown: str, allowed: set[str]) -> tuple[str, int]:
    """Remove every invented URL. Returns (markdown, URLs removed).

    A link with an invented target becomes '(unverified)'; its label is dropped
    because labels often repeat the URL. Invented bare URLs become '(unverified)'.
    """
    removed = 0

    def is_invented(url: str) -> bool:
        return normalize_url(url) not in allowed

    def replace_link(m: re.Match) -> str:
        nonlocal removed
        label, url = m.group(1), m.group(2)
        if is_invented(url):
            removed += 1
            return "(unverified)"
        if any(is_invented(u) for u in _bare_urls(label)):
            removed += 1
            return f"[source]({url})"
        return m.group(0)

    # Protect valid links while bare URLs are scanned, so their targets aren't touched.
    kept: list[str] = []

    def stash(m: re.Match) -> str:
        kept.append(replace_link(m))
        return f"\x00{len(kept) - 1}\x00"

    text = LINK_RE.sub(stash, markdown)

    def replace_bare(m: re.Match) -> str:
        nonlocal removed
        url = _clean_bare(m.group(0))
        if not is_invented(url):
            return m.group(0)
        removed += 1
        return "(unverified)" + m.group(0)[len(url):]

    text = _BARE_URL_RE.sub(replace_bare, text)
    return re.sub(r"\x00(\d+)\x00", lambda m: kept[int(m.group(1))], text), removed


_CITE_RULE = (
    "Cite sources only by their ID in square brackets, e.g. [S1], or [S1][S4] for several sources. "
    "Never write URLs or links."
)


def correction_note(source_count: int, invalid_ids: list[str] = ()) -> str:
    """Note for citations that don't point at a listed source: unknown IDs or raw URLs."""
    if not source_count:
        return (
            "CORRECTION: Your previous report cited sources, but no sources are available. Do not cite source "
            "IDs or write URLs, and do not state facts from memory; say that no sources were found."
        )
    unknown = f" ({', '.join(invalid_ids)})" if invalid_ids else ""
    return (
        f"CORRECTION: Your previous report cited sources that are not in the list{unknown}. "
        f"Only S1 to S{source_count} exist. {_CITE_RULE} Remove claims no listed source supports."
    )


def coverage_note() -> str:
    # Asking for more citations without allowing removal made the model invent sources (eval, 2026-10-23).
    return (
        "CORRECTION: Your previous report left factual claims without a source ID. Cite a source ID for each "
        f"claim, and remove claims no listed source supports. {_CITE_RULE}"
    )


async def summarize_with_guard(
    results: list[SearchResult],
    query: str,
    history: list[dict],
    summarize: Summarize,
) -> tuple[str, dict]:
    """Run the summarizer and turn its source-ID citations into links to returned sources.

    The summarizer cites [S1], [S2], ... (see number_sources); each known ID
    becomes a [domain](url) link. Unknown IDs and raw URLs not among the
    sources count as invented. At most one retry, with a correction note for
    invented citations and/or low citation coverage (zero citations, or under
    MIN_COVERAGE, when sources exist). Anything still invented after the retry
    is removed and marked '(unverified)'. Never returns an invented URL.
    """
    sources = number_sources(results)
    allowed = {normalize_url(group[0].source) for group in sources.values()}

    draft = await summarize(results, query, history)
    invalid = find_invalid_ids(draft, sources)
    invented = find_invented(draft, allowed)
    report, _ = resolve_ids(draft, sources)
    coverage = citation_coverage(report)
    low_coverage = bool(sources) and (not cited_urls(report) or coverage < MIN_COVERAGE)
    stats = {
        "citations_checked": len(cited_ids(draft)) + len(visible_urls(draft)),
        "invented_before_retry": len(invalid) + len(invented),
        "retried": False,
        "low_coverage_retry": False,
        "removed": 0,
    }
    if not invalid and not invented and not low_coverage:
        print(
            f"[citation_guard] {stats['citations_checked']} citations checked, all in sources, "
            f"coverage {coverage:.0%}",
            flush=True,
        )
        return report, stats

    notes = []
    if invalid or invented:
        notes.append(correction_note(len(sources), invalid))
    if low_coverage:
        notes.append(coverage_note())
        stats["low_coverage_retry"] = True
    print(
        f"[citation_guard] {stats['invented_before_retry']} of {stats['citations_checked']} citations not in "
        f"sources, coverage {coverage:.0%}; retrying",
        flush=True,
    )
    stats["retried"] = True
    draft = await summarize(results, query, history, correction="\n\n".join(notes))
    stats["citations_checked"] += len(cited_ids(draft)) + len(visible_urls(draft))
    report, removed_ids = resolve_ids(draft, sources)
    report, removed_urls = strip_invented(report, allowed)
    stats["removed"] = removed_ids + removed_urls
    if not stats["removed"]:
        print(f"[citation_guard] retry clean, coverage {citation_coverage(report):.0%}", flush=True)
    else:
        print(
            f"[citation_guard] retry still had invented citations; removed {removed_ids} IDs and "
            f"{removed_urls} URLs",
            flush=True,
        )
    return report, stats
