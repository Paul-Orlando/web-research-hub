"""LLM-as-judge calls via OpenRouter. The caller records token usage."""

import json
import os

import httpx

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"

_SUPPORT_PROMPT = """\
You check whether claims from a research report are supported by the source text they cite.
Judge each CLAIM only against its SOURCES text. Ignore your own knowledge.

- supported: the sources state or directly imply every factual part of the claim
- partial: the sources support some of the claim, but a number, date, name or other detail is missing or different
- unsupported: the sources do not support the claim, or contradict it

Return JSON: {"labels": [{"id": <int>, "label": "supported" | "partial" | "unsupported", "reason": "<one short sentence>"}]}\
"""

_NO_ANSWER_PROMPT = """\
The research question below may have no good answer (false premise, nonexistent data, or no search results).
Does the report clearly tell the reader that the requested information could not be found, does not exist,
or that the question's premise is wrong, instead of presenting an answer as if it had been found?

Return JSON: {"flags_missing_info": true | false, "reason": "<one short sentence>"}\
"""

_AMBIGUITY_PROMPT = """\
The research question below is ambiguous (it has several plausible meanings).
Does the report acknowledge the ambiguity, either by saying which meaning it chose or by explicitly covering
more than one meaning?

Return JSON: {"acknowledges_ambiguity": true | false, "reason": "<one short sentence>"}\
"""


async def _ask(model: str, system: str, user: str) -> dict:
    async with httpx.AsyncClient(timeout=60.0) as client:
        response = await client.post(
            OPENROUTER_URL,
            json={
                "model": model,
                "temperature": 0,
                "response_format": {"type": "json_object"},
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
            },
            headers={"Authorization": f"Bearer {os.environ['OPENROUTER_API_KEY']}"},
        )
        response.raise_for_status()
    return json.loads(response.json()["choices"][0]["message"]["content"])


async def judge_support(model: str, claims: list[dict]) -> list[dict]:
    """Returns claims annotated with label + reason, in input order."""
    if not claims:
        return []
    items = [
        {
            "id": i,
            "claim": c["claim"],
            "sources": "\n---\n".join(f"{s['url']}\n{s['summary']}" for s in c["sources"]),
        }
        for i, c in enumerate(claims)
    ]
    reply = await _ask(model, _SUPPORT_PROMPT, json.dumps(items, indent=1))
    by_id = {int(x["id"]): x for x in reply.get("labels", []) if "id" in x}
    labelled = []
    for i, c in enumerate(claims):
        x = by_id.get(i, {})
        label = x.get("label") if x.get("label") in ("supported", "partial", "unsupported") else "unlabelled"
        labelled.append({**c, "label": label, "reason": x.get("reason", "")})
    return labelled


async def judge_no_answer(model: str, question: str, report: str) -> dict:
    return await _ask(model, _NO_ANSWER_PROMPT, f"QUESTION: {question}\n\nREPORT:\n{report}")


async def judge_ambiguity(model: str, question: str, report: str) -> dict:
    return await _ask(model, _AMBIGUITY_PROMPT, f"QUESTION: {question}\n\nREPORT:\n{report}")
