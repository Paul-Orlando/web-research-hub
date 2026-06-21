import os
import json
import httpx
from datetime import datetime, timezone

from models.schemas import SearchPlannerOutput, DepthMode

OPENROUTER_BASE = "https://openrouter.ai/api/v1"
MODEL = "google/gemini-2.5-flash"

_SUBTASK_COUNT = {
    DepthMode.quick: "2",
    DepthMode.standard: "3 to 4",
    DepthMode.deep: "5 to 6",
}

_SYSTEM_PROMPT = """\
You are an expert research planner. Your task is to break down a complex research query into specific search subtasks, each focusing on a different aspect or source type.

The current date and time is: {current_datetime}

For each subtask, provide:
1. A unique string ID for the subtask (e.g., 'subtask_1', 'news_update')
2. A specific search query that focuses on one aspect of the main query
3. The source type to search (web, news, academic, specialized)
4. Time period relevance (today, last week, recent, past_year, all_time)
5. Domain focus if applicable (technology, science, health, etc.)
6. Priority level (1-highest to 5-lowest)

All fields (id, query, source_type, time_period, domain_focus, priority) are required for each subtask, except time_period and domain_focus which can be null if not applicable.

Create {subtask_count} subtasks that together will provide comprehensive coverage of the topic. Focus on different aspects, perspectives, or sources of information.

Each subtask will include the following information:

id: str
query: str
source_type: str  # e.g., "web", "news", "academic", "specialized"
time_period: Optional[str] = None  # e.g., "today", "last week", "recent", "past_year", "all_time"
domain_focus: Optional[str] = None  # e.g., "technology", "science", "health"
priority: int  # 1 (highest) to 5 (lowest)

When inferring time windows: never use a future date as start_date or end_date relative to the current date/time given above. For "recent", use at least the past 14 days (not 7) to ensure there is enough indexed content to find real results - a too-narrow window often returns zero results. After obtaining the above subtasks information, you will add two extra fields. Those correspond to start_date and end_date. Infer this information given the current date and the time_period selected. start_date and end_date should use the format as in the example below:

"start_date": "2024-06-03T06:00:00.000Z",
"end_date": "2024-06-11T05:59:59.999Z"

Return your response as a JSON object with a single key "subtasks" containing an array of subtask objects.\
"""


def _strip_fences(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        end = next((i for i in range(len(lines) - 1, 0, -1) if lines[i].strip() == "```"), len(lines))
        text = "\n".join(lines[1:end])
    return text.strip()


async def run_planner(
    query: str,
    depth_mode: DepthMode,
    history: list[dict],
) -> SearchPlannerOutput:
    api_key = os.environ["OPENROUTER_API_KEY"]
    current_datetime = datetime.now(timezone.utc).isoformat()

    system_prompt = _SYSTEM_PROMPT.format(
        current_datetime=current_datetime,
        subtask_count=_SUBTASK_COUNT[depth_mode],
    )

    user_message = query
    if history:
        context_lines = [
            f"Previous question: {h['query']}\nSummary: {h['report'][:400]}..."
            for h in history[-3:]
        ]
        user_message = (
            "Previous research context:\n"
            + "\n\n".join(context_lines)
            + f"\n\nFollow-up question: {query}"
        )

    async with httpx.AsyncClient(timeout=60.0) as client:
        response = await client.post(
            f"{OPENROUTER_BASE}/chat/completions",
            json={
                "model": MODEL,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_message},
                ],
                "response_format": {"type": "json_object"},
            },
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
        )
        response.raise_for_status()
        data = response.json()

    content = data["choices"][0]["message"]["content"]
    parsed = json.loads(_strip_fences(content))
    return SearchPlannerOutput(**parsed)
