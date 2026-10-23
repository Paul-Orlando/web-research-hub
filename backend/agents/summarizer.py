import os
from typing import Optional

import httpx

from agents.citation_guard import number_sources, source_domain
from models.schemas import SearchResult

OPENROUTER_BASE = "https://openrouter.ai/api/v1"
MODEL = "google/gemini-2.5-flash"

_SYSTEM_PROMPT = """\
Your task is to create a one-page report of the provided search results. I want to share this with my team.

- First, categorize the search results and use appropriate headers
- Then summarize the search results and add them as a list to the corresponding categories.
- Cite every factual claim with the ID of the numbered source that supports it, in square brackets: [S1]. \
If several sources support a claim, cite each one: [S1][S4].
- Use only the numbered sources. If no listed source supports a claim, leave the claim out rather than \
stating it from memory.
- Never write URLs or links.\
"""


def _format_source(source_id: str, group: list[SearchResult]) -> str:
    first = group[0]
    domain = source_domain(first.source)
    lines = [f"[{source_id}] {first.title or domain}", f"Domain: {domain}"]
    if first.publish_date:
        lines.append(f"Date: {first.publish_date}")
    # The same page can come back from several searches, each with its own summary.
    lines += [f"Summary: {r.search_result}" for r in group if r.search_result]
    return "\n".join(lines)


async def run_summarizer(
    results: list[SearchResult],
    query: str,
    history: list[dict],
    correction: Optional[str] = None,
) -> str:
    api_key = os.environ["OPENROUTER_API_KEY"]

    # Sources are numbered and sent without URLs: the model cites IDs, and the
    # citation guard maps them back to links.
    results_text = "\n\n".join(
        _format_source(source_id, group) for source_id, group in number_sources(results).items()
    )

    if not results_text:
        results_text = "No search results were returned."

    user_message = f"Research query: {query}\n\nSources:\n\n{results_text}"

    if history:
        context = "\n".join(f"Previous question: {h['query']}" for h in history[-3:])
        user_message = context + "\n\n" + user_message

    if correction:
        user_message += "\n\n" + correction

    async with httpx.AsyncClient(timeout=120.0) as client:
        response = await client.post(
            f"{OPENROUTER_BASE}/chat/completions",
            json={
                "model": MODEL,
                "messages": [
                    {"role": "system", "content": _SYSTEM_PROMPT},
                    {"role": "user", "content": user_message},
                ],
            },
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
        )
        response.raise_for_status()
        data = response.json()

    return data["choices"][0]["message"]["content"]
