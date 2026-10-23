import pytest

from agents.citation_guard import (
    correction_note,
    find_invented,
    normalize_url,
    strip_invented,
    summarize_with_guard,
)
from tests.conftest import fallback_result, make_result

RESULTS = [make_result("query a", 1), make_result("query a", 2), fallback_result("query b")]
URL1, URL2 = RESULTS[0].source, RESULTS[1].source  # https://example.com/query-a/1, /2
FAKE = "https://invented.example/story"

CLEAN = f"## Findings\n- Claim one [source]({URL1})\n- Claim two [source]({URL2}/?utm_source=x#frag)\n"
INVENTED = f"## Findings\n- Claim one [source]({URL1})\n- Claim two [Made Up]({FAKE})\n- Again [x]({FAKE})\n"


class FakeSummarizer:
    """Returns queued reports in order and records each call's correction note."""

    def __init__(self, *reports):
        self.reports = list(reports)
        self.corrections = []

    async def __call__(self, results, query, history, correction=None):
        self.corrections.append(correction)
        return self.reports.pop(0)


@pytest.mark.parametrize(
    ("a", "b"),
    [
        ("https://www.example.com/a/", "http://example.com/a"),
        ("https://example.com/a#section", "https://example.com/a"),
        ("https://example.com/a?utm_source=x&utm_medium=y", "https://example.com/a"),
        ("https://EXAMPLE.com/a?id=3&utm_campaign=z", "https://example.com/a?id=3"),
    ],
)
def test_normalize_url_equivalences(a, b):
    assert normalize_url(a) == normalize_url(b)


def test_normalize_url_keeps_meaningful_differences():
    assert normalize_url("https://example.com/a") != normalize_url("https://example.com/b")
    assert normalize_url("https://example.com/a?id=1") != normalize_url("https://example.com/a?id=2")
    assert normalize_url("https://news.example.com/a") != normalize_url("https://example.com/a")


def test_find_invented():
    allowed = {normalize_url(URL1), normalize_url(URL2)}
    assert find_invented(CLEAN, allowed) == []
    assert find_invented(INVENTED, allowed) == [FAKE]  # unique, even though cited twice


def test_strip_invented_keeps_claim_text_and_valid_links():
    allowed = {normalize_url(URL1)}
    stripped, removed = strip_invented(INVENTED, allowed)
    assert removed == 2
    assert FAKE not in stripped
    assert f"- Claim one [source]({URL1})" in stripped
    assert "- Claim two Made Up (unverified)" in stripped
    assert "- Again x (unverified)" in stripped


async def test_clean_report_passes_without_retry(capsys):
    summarize = FakeSummarizer(CLEAN)

    report, stats = await summarize_with_guard(RESULTS, "q", [], summarize)

    assert report == CLEAN
    assert summarize.corrections == [None]
    assert stats == {"citations_checked": 2, "invented_before_retry": 0, "retried": False, "removed": 0}
    assert "2 citations checked, all in sources" in capsys.readouterr().out


async def test_invented_citation_triggers_retry_with_allowed_urls():
    summarize = FakeSummarizer(INVENTED, CLEAN)

    report, stats = await summarize_with_guard(RESULTS, "q", [], summarize)

    assert report == CLEAN
    assert stats == {"citations_checked": 4, "invented_before_retry": 1, "retried": True, "removed": 0}
    note = summarize.corrections[1]
    assert URL1 in note and URL2 in note
    assert "ONLY" in note
    assert FAKE not in note


async def test_still_invented_after_retry_strips_links():
    summarize = FakeSummarizer(INVENTED, INVENTED)

    report, stats = await summarize_with_guard(RESULTS, "q", [], summarize)

    assert FAKE not in report
    assert "Made Up (unverified)" in report
    assert URL1 in report
    assert len(summarize.corrections) == 2  # exactly one retry
    assert stats == {"citations_checked": 4, "invented_before_retry": 1, "retried": True, "removed": 2}


async def test_no_sources_means_every_citation_is_invented():
    summarize = FakeSummarizer(INVENTED, INVENTED)

    report, stats = await summarize_with_guard([fallback_result("q")], "q", [], summarize)

    assert "http" not in report
    assert stats["removed"] == 3
    assert summarize.corrections[1] == correction_note([])
    assert "do not include any links" in summarize.corrections[1]


async def test_logs_counts_only(capsys):
    await summarize_with_guard(RESULTS, "q", [], FakeSummarizer(INVENTED, INVENTED))

    out = capsys.readouterr().out
    assert "[citation_guard]" in out
    assert "Claim" not in out and FAKE not in out and URL1 not in out
