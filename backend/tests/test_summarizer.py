from agents.summarizer import run_summarizer
from tests.conftest import OPENROUTER_URL, fallback_result, make_result, openrouter_reply, sent_messages


async def test_prompt_lists_numbered_sources_without_urls(respx_mock):
    results = [make_result("query a", 1), make_result("query a", 2), make_result("query b", 3)]
    route = respx_mock.post(OPENROUTER_URL).mock(return_value=openrouter_reply("report"))

    await run_summarizer(results, "topic", [])

    user_message = sent_messages(route)[1]["content"]
    assert user_message.startswith("Research query: topic")
    for i, r in enumerate(results, 1):
        assert f"[S{i}] {r.title}\nDomain: example.com\nDate: {r.publish_date}\nSummary: {r.search_result}" in user_message
    assert "http" not in user_message


async def test_repeated_url_is_one_source_with_both_summaries(respx_mock):
    first = make_result("query a", 1)
    repeat = first.model_copy(update={"query": "query b", "search_result": "second summary"})
    route = respx_mock.post(OPENROUTER_URL).mock(return_value=openrouter_reply("report"))

    await run_summarizer([first, repeat], "topic", [])

    user_message = sent_messages(route)[1]["content"]
    assert f"Summary: {first.search_result}\nSummary: second summary" in user_message
    assert "[S2]" not in user_message


async def test_fallback_entries_are_excluded_from_prompt(respx_mock):
    results = [fallback_result("query b"), make_result("query a", 1)]
    route = respx_mock.post(OPENROUTER_URL).mock(return_value=openrouter_reply("report"))

    await run_summarizer(results, "topic", [])

    user_message = sent_messages(route)[1]["content"]
    assert "[S1] Title query a #1" in user_message
    assert "No results were found" not in user_message


async def test_all_fallbacks_send_no_results_notice(respx_mock):
    route = respx_mock.post(OPENROUTER_URL).mock(return_value=openrouter_reply("report"))

    await run_summarizer([fallback_result("q1"), fallback_result("q2")], "topic", [])

    assert "No search results were returned." in sent_messages(route)[1]["content"]


async def test_correction_note_is_appended_to_user_message(respx_mock):
    route = respx_mock.post(OPENROUTER_URL).mock(return_value=openrouter_reply("report"))

    await run_summarizer([make_result("query a", 1)], "topic", [])
    assert "CORRECTION" not in sent_messages(route)[1]["content"]

    await run_summarizer([make_result("query a", 1)], "topic", [], correction="CORRECTION: use only X")
    assert sent_messages(route)[1]["content"].endswith("\n\nCORRECTION: use only X")


async def test_system_prompt_asks_for_source_ids_not_urls(respx_mock):
    route = respx_mock.post(OPENROUTER_URL).mock(return_value=openrouter_reply("- Chip sales grew [S1]"))

    output = await run_summarizer([make_result("query a", 1)], "topic", [])

    system = sent_messages(route)[0]["content"]
    assert "[S1]" in system and "[S1][S4]" in system
    assert "leave the claim out rather than stating it from memory" in system
    assert "Never write URLs" in system
    assert "[source](url)" not in system
    assert output == "- Chip sales grew [S1]"  # the citation guard maps IDs to links, not the summarizer
