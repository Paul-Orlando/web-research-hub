import json

import pytest
from fastapi.testclient import TestClient

import main
from models.schemas import SearchPlannerOutput
from tests.conftest import fallback_result, make_result, make_subtask

SESSION = "test-session"
# Deliberately cites URLs the orchestrator never returned.
REPORT = "# Report\n- Claim [Other](https://not-a-search-result.com/z)\n"
GUARDED_REPORT = "# Report\n- Claim (unverified)\n"


@pytest.fixture
def client():
    return TestClient(main.app)


@pytest.fixture
def pipeline(monkeypatch):
    """Mock all three agents; returns a dict recording what they received."""
    seen = {}
    subtasks = [make_subtask(i) for i in range(3)]
    results_by_query = {
        "query 0": [make_result("query 0", 1), make_result("query 0", 2)],
        "query 1": [fallback_result("query 1")],
        "query 2": [make_result("query 2", 3)],
    }

    async def fake_planner(query, depth_mode, history):
        seen["planner"] = (query, depth_mode, list(history))
        return SearchPlannerOutput(subtasks=subtasks)

    async def fake_subtask(subtask, depth_mode):
        seen.setdefault("subtask_order", []).append(subtask.id)
        return results_by_query[subtask.query]

    async def fake_summarizer(results, query, history, correction=None):
        seen["summarizer_results"] = results
        seen.setdefault("corrections", []).append(correction)
        return REPORT

    monkeypatch.setattr(main, "run_planner", fake_planner)
    monkeypatch.setattr(main, "run_subtask", fake_subtask)
    monkeypatch.setattr(main, "run_summarizer", fake_summarizer)
    seen["results_by_query"] = results_by_query
    return seen


def parse_sse(body: str) -> list[tuple[str, dict]]:
    events = []
    for block in body.replace("\r\n", "\n").split("\n\n"):
        event, data = None, None
        for line in block.split("\n"):
            if line.startswith("event:"):
                event = line[len("event:"):].strip()
            elif line.startswith("data:"):
                data = json.loads(line[len("data:"):].strip())
        if event:
            events.append((event, data))
    return events


def run_research(client, query="AI chips"):
    response = client.post("/research", json={"query": query, "depth_mode": "standard", "session_id": SESSION})
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    return parse_sse(response.text)


def test_health(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_research_streams_expected_events(client, pipeline):
    events = run_research(client)

    assert [e for e, _ in events] == [
        "stage", "subtasks", "stage",
        "subtask_complete", "subtask_complete", "subtask_complete",
        "stage", "report", "done",
    ]
    stages = [d["stage"] for e, d in events if e == "stage"]
    assert stages == ["planning", "searching", "synthesizing"]

    subtasks_event = events[1][1]
    assert subtasks_event["count"] == 3
    assert [s["id"] for s in subtasks_event["subtasks"]] == ["subtask_0", "subtask_1", "subtask_2"]

    completes = [d for e, d in events if e == "subtask_complete"]
    assert [(c["id"], c["index"], c["total"]) for c in completes] == [
        ("subtask_0", 0, 3), ("subtask_1", 1, 3), ("subtask_2", 2, 3),
    ]
    assert len(completes[0]["sources"]) == 2
    assert completes[1]["sources"] == []  # fallback still produces an entry

    # REPORT cites a URL the orchestrator never returned: the guard retries once,
    # then strips the link.
    assert events[-2][1] == {
        "markdown": GUARDED_REPORT,
        "guard": {"citations_checked": 2, "invented_before_retry": 1, "retried": True, "low_coverage_retry": False, "removed": 1},
    }
    assert pipeline["corrections"][0] is None
    assert "https://example.com/query-0/1" in pipeline["corrections"][1]
    assert pipeline["subtask_order"] == ["subtask_0", "subtask_1", "subtask_2"]
    assert [r.query for r in pipeline["summarizer_results"]] == ["query 0", "query 0", "query 1", "query 2"]


def test_research_error_emits_error_event(client, monkeypatch):
    async def failing_planner(query, depth_mode, history):
        raise RuntimeError("planner exploded")

    monkeypatch.setattr(main, "run_planner", failing_planner)

    events = run_research(client)

    assert events[0][0] == "stage"
    assert events[-1] == ("error", {"message": "planner exploded"})


def test_source_list_built_from_orchestrator_results(client, pipeline):
    run_research(client)

    expected = [
        {"url": r.source, "publish_date": r.publish_date, "title": r.title}
        for results in pipeline["results_by_query"].values()
        for r in results
        if r.source
    ]
    sources = client.get(f"/session/{SESSION}/sources").json()
    assert sources == expected
    assert all("not-a-search-result.com" not in s["url"] for s in sources)


def test_follow_up_receives_history(client, pipeline):
    run_research(client, "first")
    run_research(client, "second")

    assert pipeline["planner"] == ("second", main.DepthMode.standard, [{"query": "first", "report": GUARDED_REPORT}])


def test_delete_session_clears_it(client, pipeline):
    run_research(client)
    assert client.get(f"/session/{SESSION}/history").json() != []

    response = client.delete(f"/session/{SESSION}")

    assert response.status_code == 200
    assert response.json() == {"deleted": SESSION}
    assert client.get(f"/session/{SESSION}/history").json() == []
    assert client.get(f"/session/{SESSION}/sources").json() == []
