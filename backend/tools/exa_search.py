import json
import os
from typing import Optional

import httpx

MCP_SERVER_URL = os.getenv("MCP_SERVER_URL")

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
    try:
        payload = {
            "jsonrpc": "2.0",
            "method": "tools/call",
            "id": 1,
            "params": {
                "name": "web_search",
                "arguments": {
                    "query": query,
                    "num_results": num_results,
                    "start_date": start_date,
                    "end_date": end_date,
                },
            },
        }

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{MCP_SERVER_URL}/mcp",
                json=payload,
                headers={"Content-Type": "application/json"},
            )
            response.raise_for_status()
            data = response.json()

        # MCP returns result.content[0].text as a JSON string
        text = data["result"]["content"][0]["text"]
        parsed = json.loads(text)

        # Handle both {"results": [...]} and [...] top-level shapes
        if isinstance(parsed, list):
            results = parsed
        else:
            results = parsed.get("results", [])

        if not results:
            return [_FALLBACK(query)]

        return [
            {
                "query": query,
                "search_result": r.get("summary") or r.get("text") or "",
                "source": r.get("url") or "",
                "publish_date": r.get("publishedDate") or r.get("publish_date") or "",
                "title": r.get("title") or "",
            }
            for r in results
        ]
    except Exception:
        return [_FALLBACK(query)]
