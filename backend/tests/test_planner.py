import re
from datetime import datetime, timedelta, timezone

import pytest

from agents.planner import run_planner
from models.schemas import DepthMode, SearchPlannerOutput
from tests.conftest import OPENROUTER_URL, openrouter_reply, sent_messages


def subtask_dicts(n: int, start: str = "2026-10-01T00:00:00.000Z", end: str = "2026-10-15T23:59:59.999Z"):
    return [
        {
            "id": f"subtask_{i}",
            "query": f"aspect {i}",
            "source_type": "news",
            "time_period": "recent",
            "domain_focus": "technology",
            "priority": i,
            "start_date": start,
            "end_date": end,
        }
        for i in range(1, n + 1)
    ]


async def test_parses_valid_json_into_subtasks(respx_mock):
    expected = subtask_dicts(3)
    respx_mock.post(OPENROUTER_URL).mock(return_value=openrouter_reply({"subtasks": expected}))

    plan = await run_planner("AI chips", DepthMode.standard, [])

    assert isinstance(plan, SearchPlannerOutput)
    assert [s.model_dump() for s in plan.subtasks] == expected


async def test_parses_json_wrapped_in_code_fences(respx_mock):
    import json

    fenced = "```json\n" + json.dumps({"subtasks": subtask_dicts(2)}) + "\n```"
    respx_mock.post(OPENROUTER_URL).mock(return_value=openrouter_reply(fenced))

    plan = await run_planner("AI chips", DepthMode.quick, [])

    assert [s.id for s in plan.subtasks] == ["subtask_1", "subtask_2"]


@pytest.mark.parametrize(
    ("depth", "requested", "reply_counts"),
    [
        (DepthMode.quick, "2", [2]),
        (DepthMode.standard, "3 to 4", [3, 4]),
        (DepthMode.deep, "5 to 6", [5, 6]),
    ],
)
async def test_subtask_count_matches_depth(respx_mock, depth, requested, reply_counts):
    for n in reply_counts:
        route = respx_mock.post(OPENROUTER_URL).mock(return_value=openrouter_reply({"subtasks": subtask_dicts(n)}))

        plan = await run_planner("AI chips", depth, [])

        system_prompt = sent_messages(route)[0]["content"]
        assert f"Create {requested} subtasks" in system_prompt
        assert len(plan.subtasks) == n


async def test_prompt_uses_current_date_and_forbids_future_dates(respx_mock):
    now = datetime.now(timezone.utc)
    start = (now - timedelta(days=14)).strftime("%Y-%m-%dT%H:%M:%S.000Z")
    end = now.strftime("%Y-%m-%dT%H:%M:%S.000Z")
    route = respx_mock.post(OPENROUTER_URL).mock(
        return_value=openrouter_reply({"subtasks": subtask_dicts(2, start=start, end=end)})
    )

    plan = await run_planner("AI chips", DepthMode.quick, [])
    after = datetime.now(timezone.utc)

    system_prompt = sent_messages(route)[0]["content"]
    match = re.search(r"The current date and time is: (\S+)", system_prompt)
    assert match
    prompt_now = datetime.fromisoformat(match.group(1))
    assert now - timedelta(seconds=5) <= prompt_now <= after
    assert "never use a future date" in system_prompt

    for s in plan.subtasks:
        s_start = datetime.fromisoformat(s.start_date.replace("Z", "+00:00"))
        s_end = datetime.fromisoformat(s.end_date.replace("Z", "+00:00"))
        assert s_start <= s_end <= after


async def test_history_is_sent_as_follow_up_context(respx_mock):
    route = respx_mock.post(OPENROUTER_URL).mock(return_value=openrouter_reply({"subtasks": subtask_dicts(2)}))
    history = [{"query": "first question", "report": "first report"}]

    await run_planner("second question", DepthMode.quick, history)

    user_message = sent_messages(route)[1]["content"]
    assert "Previous question: first question" in user_message
    assert user_message.endswith("Follow-up question: second question")
