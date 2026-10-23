import json

import httpx
import pytest

from tools.exa_search import exa_search
from tests.conftest import FALLBACK_TEXT, MCP_URL

FALLBACK = [{"query": "q", "search_result": FALLBACK_TEXT, "source": "", "publish_date": "", "title": ""}]

EXA_RESULTS = [
    {"url": "https://a.com", "title": "A", "summary": "sum A", "published_date": "2026-10-01"},
    {"url": "https://b.com", "title": "B", "text": "text B", "publishedDate": "2026-10-02"},
]


def tool_payload(parsed) -> dict:
    return {"jsonrpc": "2.0", "id": 1, "result": {"content": [{"type": "text", "text": json.dumps(parsed)}]}}


def sse_body(payload: dict) -> str:
    return f"event: message\ndata: {json.dumps(payload)}\n\n"


def mock_mcp(respx_mock, tool_response: httpx.Response, init_response: httpx.Response | None = None):
    """Route initialize and tools/call (both POST /mcp) to separate responses."""
    init_response = init_response or httpx.Response(200, headers={"mcp-session-id": "sess-123"}, json={})
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        method = json.loads(request.content)["method"]
        return init_response if method == "initialize" else tool_response

    respx_mock.post(MCP_URL).mock(side_effect=handler)
    return calls


async def test_sends_api_key_and_session_id_headers(respx_mock):
    calls = mock_mcp(respx_mock, httpx.Response(200, text=sse_body(tool_payload({"results": EXA_RESULTS}))))

    await exa_search("q", "2026-10-01T00:00:00.000Z", None, num_results=2)

    init, tool = calls
    assert json.loads(init.content)["method"] == "initialize"
    assert init.headers["X-API-Key"] == "test-key"
    assert json.loads(tool.content)["method"] == "tools/call"
    assert tool.headers["X-API-Key"] == "test-key"
    assert tool.headers["mcp-session-id"] == "sess-123"
    arguments = json.loads(tool.content)["params"]["arguments"]
    assert arguments == {"query": "q", "num_results": 2, "start_date": "2026-10-01T00:00:00.000Z"}


async def test_parses_sse_response(respx_mock):
    mock_mcp(respx_mock, httpx.Response(200, text=sse_body(tool_payload({"results": EXA_RESULTS}))))

    results = await exa_search("q", None, None)

    assert results == [
        {"query": "q", "search_result": "sum A", "source": "https://a.com", "publish_date": "2026-10-01", "title": "A"},
        {"query": "q", "search_result": "text B", "source": "https://b.com", "publish_date": "2026-10-02", "title": "B"},
    ]


async def test_parses_plain_json_list_response(respx_mock):
    mock_mcp(respx_mock, httpx.Response(200, json=tool_payload(EXA_RESULTS)))

    results = await exa_search("q", None, None)

    assert [r["source"] for r in results] == ["https://a.com", "https://b.com"]


async def test_empty_results_return_fallback(respx_mock):
    mock_mcp(respx_mock, httpx.Response(200, text=sse_body(tool_payload({"results": []}))))

    assert await exa_search("q", None, None) == FALLBACK


@pytest.mark.parametrize(
    "case",
    ["init_http_error", "tool_http_error", "timeout", "non_json_body", "missing_content", "non_json_tool_text"],
)
async def test_failures_return_fallback(respx_mock, case):
    ok_init = httpx.Response(200, headers={"mcp-session-id": "sess-123"}, json={})
    if case == "init_http_error":
        mock_mcp(respx_mock, httpx.Response(200, json=tool_payload(EXA_RESULTS)), httpx.Response(500))
    elif case == "tool_http_error":
        mock_mcp(respx_mock, httpx.Response(502, text="bad gateway"), ok_init)
    elif case == "timeout":
        respx_mock.post(MCP_URL).mock(side_effect=httpx.ReadTimeout("timed out"))
    elif case == "non_json_body":
        mock_mcp(respx_mock, httpx.Response(200, text="<html>oops</html>"), ok_init)
    elif case == "missing_content":
        mock_mcp(respx_mock, httpx.Response(200, json={"jsonrpc": "2.0", "id": 1, "error": {"code": -1}}), ok_init)
    elif case == "non_json_tool_text":
        payload = {"jsonrpc": "2.0", "id": 1, "result": {"content": [{"type": "text", "text": "not json"}]}}
        mock_mcp(respx_mock, httpx.Response(200, text=sse_body(payload)), ok_init)

    assert await exa_search("q", None, None) == FALLBACK
