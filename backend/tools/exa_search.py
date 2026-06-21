import os
from typing import Optional
import httpx

EXA_API_URL = "https://api.exa.ai/search"

_FALLBACK = lambda query: {
    "query": query,
    "search_result": "No results were found for this search query within the specified date range.",
    "source": "",
    "publish_date": "",
    "title": "",
}


async def exa_search(
    query: str,
    start_date: Optional[str],
    end_date: Optional[str],
    num_results: int = 4,
) -> list[dict]:
    api_key = os.environ["EXA_API_KEY"]

    payload: dict = {
        "query": query,
        "numResults": num_results,
        "contents": {
            "summary": {"query": "Summarize the essential results"}
        },
    }
    if start_date:
        payload["startPublishedDate"] = start_date
    if end_date:
        payload["endPublishedDate"] = end_date

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                EXA_API_URL,
                json=payload,
                headers={
                    "x-api-key": api_key,
                    "Content-Type": "application/json",
                },
            )
            response.raise_for_status()
            data = response.json()

        results = data.get("results", [])
        if not results:
            return [_FALLBACK(query)]

        return [
            {
                "query": query,
                "search_result": r.get("summary") or "",
                "source": r.get("url") or "",
                "publish_date": r.get("publishedDate") or "",
                "title": r.get("title") or "",
            }
            for r in results
        ]
    except Exception:
        return [_FALLBACK(query)]
