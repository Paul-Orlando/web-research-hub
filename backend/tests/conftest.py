import json
import os

# Set before any app module is imported: tools/exa_search.py and main.py read
# these at import time. Assigned (not setdefault) so a local .env can't leak in.
os.environ["OPENROUTER_API_KEY"] = "test-openrouter-key"
os.environ["MCP_SERVER_URL"] = "http://mcp.test"
os.environ["MCP_API_KEY"] = "test-key"
os.environ["EXA_API_KEY"] = "test-exa-key"

import httpx
import pytest

from models.schemas import SearchResult, SearchSubtask
from session_store import session_store

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
MCP_URL = "http://mcp.test/mcp"
FALLBACK_TEXT = "No results were found for this search query within the specified date range."


@pytest.fixture(autouse=True)
def clear_sessions():
    session_store._store.clear()
    yield
    session_store._store.clear()


def openrouter_reply(content) -> httpx.Response:
    """Fake OpenRouter chat-completion response; dicts are JSON-encoded."""
    if not isinstance(content, str):
        content = json.dumps(content)
    return httpx.Response(200, json={"choices": [{"message": {"content": content}}]})


def sent_messages(route) -> list[dict]:
    """Messages from the last request a respx route received."""
    return json.loads(route.calls.last.request.content)["messages"]


def make_subtask(i: int, **overrides) -> SearchSubtask:
    data = {
        "id": f"subtask_{i}",
        "query": f"query {i}",
        "source_type": "web",
        "time_period": "recent",
        "domain_focus": None,
        "priority": 1,
        "start_date": "2026-10-01T00:00:00.000Z",
        "end_date": "2026-10-15T23:59:59.999Z",
    }
    data.update(overrides)
    return SearchSubtask(**data)


def make_result(query: str, n: int) -> SearchResult:
    return SearchResult(
        query=query,
        search_result=f"content for {query} #{n}",
        source=f"https://example.com/{query.replace(' ', '-')}/{n}",
        publish_date="2026-10-10",
        title=f"Title {query} #{n}",
    )


def fallback_result(query: str) -> SearchResult:
    return SearchResult(query=query, search_result=FALLBACK_TEXT, source="", publish_date="", title="")
