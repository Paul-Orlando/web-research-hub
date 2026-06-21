import os
import httpx

from models.schemas import SearchResult

OPENROUTER_BASE = "https://openrouter.ai/api/v1"
MODEL = "google/gemini-2.5-flash"

_SYSTEM_PROMPT = """\
Your task is to create a one-page report of the provided search results. I want to share this with my team.

- First, categorize the search results and use appropriate headers
- Then summarize the search results and add them as a list to the corresponding categories.
- Make sure to include the citation using this format [source](url)\
"""


async def run_summarizer(
    results: list[SearchResult],
    query: str,
    history: list[dict],
) -> str:
    api_key = os.environ["OPENROUTER_API_KEY"]

    results_text = "\n\n".join(
        f"Query: {r.query}\nSource: {r.source}\nDate: {r.publish_date}\nContent: {r.search_result}"
        for r in results
        if r.search_result and r.search_result != "No results were found for this search query within the specified date range."
    )

    if not results_text:
        results_text = "No search results were returned."

    user_message = f"Research query: {query}\n\nSearch results:\n\n{results_text}"

    if history:
        context = "\n".join(f"Previous question: {h['query']}" for h in history[-3:])
        user_message = context + "\n\n" + user_message

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
