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
        # Only include date args when they have values — passing null
        # causes the MCP server to apply its own default date range.
        arguments: dict = {"query": query, "num_results": num_results}
        if start_date:
            arguments["start_date"] = start_date
        if end_date:
            arguments["end_date"] = end_date

        payload = {
            "jsonrpc": "2.0",
            "method": "tools/call",
            "id": 1,
            "params": {
                "name": "web_search",
                "arguments": arguments,
            },
        }

        print(f"[exa_search] MCP request body: {json.dumps(payload)}")

        async with httpx.AsyncClient(timeout=30.0) as client:
            init_response = await client.post(
                f"{MCP_SERVER_URL}/mcp",
                json={
                    "jsonrpc": "2.0",
                    "method": "initialize",
                    "id": 0,
                    "params": {
                        "protocolVersion": "2024-11-05",
                        "capabilities": {},
                        "clientInfo": {"name": "web-research-hub", "version": "1.0"},
                    },
                },
                headers={
                    "Content-Type": "application/json",
                    "Accept": "application/json, text/event-stream",
                },
            )
            init_response.raise_for_status()
            session_id = init_response.headers.get("mcp-session-id")
            print(f"[exa_search] MCP session_id: {session_id}")

            tool_headers = {
                "Content-Type": "application/json",
                "Accept": "application/json, text/event-stream",
            }
            if session_id:
                tool_headers["mcp-session-id"] = session_id

            response = await client.post(
                f"{MCP_SERVER_URL}/mcp",
                json=payload,
                headers=tool_headers,
            )
            response.raise_for_status()
            data = response.json()

        print(f"[exa_search] raw MCP response: {json.dumps(data)[:2000]}")

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
                # MCP server returns "published_date" (not "publishedDate")
                "publish_date": r.get("published_date") or r.get("publishedDate") or r.get("publish_date") or "",
                "title": r.get("title") or "",
            }
            for r in results
        ]
    except Exception as exc:
        print(f"[exa_search] error: {exc}")
        return [_FALLBACK(query)]
