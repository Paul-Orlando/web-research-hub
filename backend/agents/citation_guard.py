import re
from typing import Awaitable, Callable
from urllib.parse import parse_qsl, urlencode, urlparse

from models.schemas import SearchResult

# URLs may contain one level of balanced parentheses, e.g. .../S0968-0004(20)30150-X
LINK_RE = re.compile(r"\[([^\]]+)\]\((https?://(?:[^()\s]|\([^()\s]*\))+)\)")
_BARE_URL_RE = re.compile(r"https?://[^\s<>\[\]\"'`]+")
_BULLET_RE = re.compile(r"^(?:[-*+]|\d+[.)])\s+")
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+(?=[A-Z\[\"(])")
MIN_COVERAGE = 0.5

Summarize = Callable[..., Awaitable[str]]


def normalize_url(url: str) -> str:
    """Comparable form: no scheme, no www., no trailing slash, fragment or utm_* params."""
    parsed = urlparse(url.strip())
    host = parsed.netloc.lower().removeprefix("www.")
    path = parsed.path.rstrip("/")
    query = urlencode([(k, v) for k, v in parse_qsl(parsed.query) if not k.lower().startswith("utm_")])
    return host + path + (f"?{query}" if query else "")


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


_FORMAT_RULE = (
    "Write every citation as a markdown link in exactly this form: [source](URL). "
    "Never write a bare URL, and never put URLs in square brackets without the (URL) part."
)


def correction_note(allowed_urls: list[str]) -> str:
    if not allowed_urls:
        return (
            "CORRECTION: Your previous report cited URLs that were not in the search results. "
            "No source URLs are available, so do not include any URLs or links."
        )
    return (
        "CORRECTION: Your previous report cited URLs that were not in the search results. "
        f"{_FORMAT_RULE} Cite ONLY the URLs below (copy each URL exactly), and drop any claim you cannot "
        "support with them:\n"
        + "\n".join(f"- {u}" for u in allowed_urls)
    )


def coverage_note(allowed_urls: list[str]) -> str:
    return (
        "CORRECTION: Your previous report left factual claims without citations. Every factual claim "
        "(each bullet and each sentence that states a fact) must include a citation. "
        f"{_FORMAT_RULE} Use only the URLs below, and drop any claim you cannot cite:\n"
        + "\n".join(f"- {u}" for u in allowed_urls)
    )


async def summarize_with_guard(
    results: list[SearchResult],
    query: str,
    history: list[dict],
    summarize: Summarize,
) -> tuple[str, dict]:
    """Run the summarizer and ensure every citation points at a returned source.

    At most one retry, with a correction note for invented citations and/or
    low citation coverage (zero citations, or under MIN_COVERAGE, when sources
    exist). If any visible URL is still invented after the retry, it is
    removed. Never returns an invented URL.
    """
    allowed_urls = list(dict.fromkeys(r.source for r in results if r.source))
    allowed = {normalize_url(u) for u in allowed_urls}

    report = await summarize(results, query, history)
    invented = find_invented(report, allowed)
    coverage = citation_coverage(report)
    low_coverage = bool(allowed_urls) and (not cited_urls(report) or coverage < MIN_COVERAGE)
    stats = {
        "citations_checked": len(visible_urls(report)),
        "invented_before_retry": len(invented),
        "retried": False,
        "low_coverage_retry": False,
        "removed": 0,
    }
    if not invented and not low_coverage:
        print(
            f"[citation_guard] {stats['citations_checked']} citations checked, all in sources, "
            f"coverage {coverage:.0%}",
            flush=True,
        )
        return report, stats

    notes = []
    if invented:
        notes.append(correction_note(allowed_urls))
    if low_coverage:
        notes.append(coverage_note(allowed_urls))
        stats["low_coverage_retry"] = True
    print(
        f"[citation_guard] {len(invented)} of {stats['citations_checked']} citations not in sources, "
        f"coverage {coverage:.0%}; retrying",
        flush=True,
    )
    stats["retried"] = True
    report = await summarize(results, query, history, correction="\n\n".join(notes))
    stats["citations_checked"] += len(visible_urls(report))
    invented = find_invented(report, allowed)
    if not invented:
        print(f"[citation_guard] retry clean, coverage {citation_coverage(report):.0%}", flush=True)
        return report, stats

    report, stats["removed"] = strip_invented(report, allowed)
    print(
        f"[citation_guard] retry still had {len(invented)} invented citations; removed {stats['removed']} URLs",
        flush=True,
    )
    return report, stats
