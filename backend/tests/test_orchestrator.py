import pytest

from agents import orchestrator
from agents.orchestrator import run_subtask
from models.schemas import DepthMode, SearchResult
from tools.exa_search import _FALLBACK
from tests.conftest import FALLBACK_TEXT, make_subtask


class SearchCalls(list):
    """Recorded exa_search calls; `responses` maps query -> raw results."""

    def __init__(self):
        super().__init__()
        self.responses: dict[str, list[dict]] = {}


@pytest.fixture
def search_calls(monkeypatch):
    """Patch exa_search; queries without a response get the real fallback."""
    calls = SearchCalls()

    async def fake_exa_search(query, start_date, end_date, num_results=4):
        calls.append({"query": query, "start_date": start_date, "end_date": end_date, "num_results": num_results})
        return calls.responses.get(query) or [_FALLBACK(query)]

    monkeypatch.setattr(orchestrator, "exa_search", fake_exa_search)
    return calls


def raw_result(query: str, n: int) -> dict:
    return {
        "query": query,
        "search_result": f"content {n}",
        "source": f"https://example.com/{n}",
        "publish_date": "2026-10-10",
        "title": f"Title {n}",
    }


async def test_empty_search_yields_fallback_entry_per_subtask(search_calls):
    subtasks = [make_subtask(i) for i in range(3)]

    per_subtask = [await run_subtask(s, DepthMode.standard) for s in subtasks]

    for subtask, results in zip(subtasks, per_subtask):
        assert len(results) == 1
        assert isinstance(results[0], SearchResult)
        assert results[0].query == subtask.query
        assert results[0].search_result == FALLBACK_TEXT
        assert results[0].source == ""


async def test_results_collected_in_subtask_order(search_calls):
    subtasks = [make_subtask(i) for i in range(3)]
    search_calls.responses["query 0"] = [raw_result("query 0", 1), raw_result("query 0", 2)]
    # "query 1" falls back
    search_calls.responses["query 2"] = [raw_result("query 2", 3)]

    all_results = []
    for s in subtasks:
        all_results.extend(await run_subtask(s, DepthMode.standard))

    assert [r.query for r in all_results] == ["query 0", "query 0", "query 1", "query 2"]
    assert [r.source for r in all_results] == [
        "https://example.com/1",
        "https://example.com/2",
        "",
        "https://example.com/3",
    ]
    assert [c["query"] for c in search_calls] == ["query 0", "query 1", "query 2"]


@pytest.mark.parametrize(("depth", "expected"), [(DepthMode.quick, 3), (DepthMode.standard, 4), (DepthMode.deep, 5)])
async def test_depth_sets_num_results_and_dates_forwarded(search_calls, depth, expected):
    subtask = make_subtask(1)

    await run_subtask(subtask, depth)

    assert search_calls[-1] == {
        "query": subtask.query,
        "start_date": subtask.start_date,
        "end_date": subtask.end_date,
        "num_results": expected,
    }


async def test_empty_dates_forwarded_as_none(search_calls):
    await run_subtask(make_subtask(1, start_date="", end_date=None), DepthMode.quick)

    assert search_calls[-1]["start_date"] is None
    assert search_calls[-1]["end_date"] is None
