import re

from agents.summarizer import run_summarizer
from tests.conftest import OPENROUTER_URL, fallback_result, make_result, openrouter_reply, sent_messages

CITATION = re.compile(r"\[[^\]]+\]\(https?://[^)\s]+\)")


async def test_prompt_includes_all_sources(respx_mock):
    results = [make_result("query a", 1), make_result("query a", 2), make_result("query b", 3)]
    route = respx_mock.post(OPENROUTER_URL).mock(return_value=openrouter_reply("report"))

    await run_summarizer(results, "topic", [])

    user_message = sent_messages(route)[1]["content"]
    assert user_message.startswith("Research query: topic")
    for r in results:
        assert f"Source: {r.source}" in user_message
        assert r.search_result in user_message


async def test_fallback_entries_are_excluded_from_prompt(respx_mock):
    results = [make_result("query a", 1), fallback_result("query b")]
    route = respx_mock.post(OPENROUTER_URL).mock(return_value=openrouter_reply("report"))

    await run_summarizer(results, "topic", [])

    user_message = sent_messages(route)[1]["content"]
    assert "Query: query a" in user_message
    assert "Query: query b" not in user_message


async def test_all_fallbacks_send_no_results_notice(respx_mock):
    route = respx_mock.post(OPENROUTER_URL).mock(return_value=openrouter_reply("report"))

    await run_summarizer([fallback_result("q1"), fallback_result("q2")], "topic", [])

    assert "No search results were returned." in sent_messages(route)[1]["content"]


async def test_citations_use_markdown_link_format(respx_mock):
    report = (
        "## Findings\n"
        "- Chip sales grew 20% [Reuters](https://reuters.com/x)\n"
        "- New fab announced [TechCrunch](https://techcrunch.com/y)\n"
    )
    route = respx_mock.post(OPENROUTER_URL).mock(return_value=openrouter_reply(report))

    output = await run_summarizer([make_result("query a", 1)], "topic", [])

    assert "[source](url)" in sent_messages(route)[0]["content"]
    assert output == report
    citations = CITATION.findall(output)
    assert citations == ["[Reuters](https://reuters.com/x)", "[TechCrunch](https://techcrunch.com/y)"]
