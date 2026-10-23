import re
from typing import Awaitable, Callable
from urllib.parse import parse_qsl, urlencode, urlparse

from models.schemas import SearchResult

LINK_RE = re.compile(r"\[([^\]]+)\]\((https?://[^)\s]+)\)")

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


def find_invented(markdown: str, allowed: set[str]) -> list[str]:
    """Cited URLs whose normalized form isn't in `allowed` (already normalized)."""
    return [url for url in cited_urls(markdown) if normalize_url(url) not in allowed]


def strip_invented(markdown: str, allowed: set[str]) -> tuple[str, int]:
    """Replace invented [text](url) links with 'text (unverified)'. Returns (markdown, links removed)."""
    removed = 0

    def replace(m: re.Match) -> str:
        nonlocal removed
        if normalize_url(m.group(2)) in allowed:
            return m.group(0)
        removed += 1
        return f"{m.group(1)} (unverified)"

    return LINK_RE.sub(replace, markdown), removed


def correction_note(allowed_urls: list[str]) -> str:
    if not allowed_urls:
        return (
            "CORRECTION: Your previous report cited URLs that were not in the search results. "
            "No source URLs are available, so do not include any links."
        )
    return (
        "CORRECTION: Your previous report cited URLs that were not in the search results. "
        "Cite ONLY these URLs, exactly as written, and drop any claim you cannot support with them:\n"
        + "\n".join(f"- {u}" for u in allowed_urls)
    )


async def summarize_with_guard(
    results: list[SearchResult],
    query: str,
    history: list[dict],
    summarize: Summarize,
) -> tuple[str, dict]:
    """Run the summarizer and ensure every citation points at a returned source.

    One retry with a correction note; if citations are still invented, their
    links are removed. Never returns an invented URL.
    """
    allowed_urls = list(dict.fromkeys(r.source for r in results if r.source))
    allowed = {normalize_url(u) for u in allowed_urls}

    report = await summarize(results, query, history)
    invented = find_invented(report, allowed)
    stats = {
        "citations_checked": len(cited_urls(report)),
        "invented_before_retry": len(invented),
        "retried": False,
        "removed": 0,
    }
    if not invented:
        print(f"[citation_guard] {stats['citations_checked']} citations checked, all in sources", flush=True)
        return report, stats

    print(
        f"[citation_guard] {len(invented)} of {stats['citations_checked']} citations not in sources; retrying",
        flush=True,
    )
    stats["retried"] = True
    report = await summarize(results, query, history, correction=correction_note(allowed_urls))
    stats["citations_checked"] += len(cited_urls(report))
    invented = find_invented(report, allowed)
    if not invented:
        print("[citation_guard] retry clean", flush=True)
        return report, stats

    report, stats["removed"] = strip_invented(report, allowed)
    print(
        f"[citation_guard] retry still had {len(invented)} invented citations; removed {stats['removed']} links",
        flush=True,
    )
    return report, stats
