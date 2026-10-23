import pytest

from agents.citation_guard import (
    citation_coverage,
    correction_note,
    coverage_note,
    find_invented,
    normalize_url,
    report_units,
    strip_invented,
    summarize_with_guard,
    visible_urls,
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


def test_strip_invented_drops_link_and_label_keeps_claim_and_valid_links():
    allowed = {normalize_url(URL1)}
    stripped, removed = strip_invented(INVENTED, allowed)
    assert removed == 2
    assert FAKE not in stripped
    assert f"- Claim one [source]({URL1})" in stripped
    assert "- Claim two (unverified)" in stripped
    assert "- Again (unverified)" in stripped
    assert "Made Up" not in stripped


async def test_clean_report_passes_without_retry(capsys):
    summarize = FakeSummarizer(CLEAN)

    report, stats = await summarize_with_guard(RESULTS, "q", [], summarize)

    assert report == CLEAN
    assert summarize.corrections == [None]
    assert stats == {"citations_checked": 2, "invented_before_retry": 0, "retried": False, "low_coverage_retry": False, "removed": 0}
    assert "2 citations checked, all in sources" in capsys.readouterr().out


async def test_invented_citation_triggers_retry_with_allowed_urls():
    summarize = FakeSummarizer(INVENTED, CLEAN)

    report, stats = await summarize_with_guard(RESULTS, "q", [], summarize)

    assert report == CLEAN
    assert stats == {"citations_checked": 4, "invented_before_retry": 1, "retried": True, "low_coverage_retry": False, "removed": 0}
    note = summarize.corrections[1]
    assert URL1 in note and URL2 in note
    assert "ONLY" in note
    assert FAKE not in note


async def test_still_invented_after_retry_strips_links():
    summarize = FakeSummarizer(INVENTED, INVENTED)

    report, stats = await summarize_with_guard(RESULTS, "q", [], summarize)

    assert FAKE not in report
    assert "- Claim two (unverified)" in report
    assert URL1 in report
    assert len(summarize.corrections) == 2  # exactly one retry
    assert stats == {"citations_checked": 4, "invented_before_retry": 1, "retried": True, "low_coverage_retry": False, "removed": 2}


async def test_no_sources_means_every_citation_is_invented():
    summarize = FakeSummarizer(INVENTED, INVENTED)

    report, stats = await summarize_with_guard([fallback_result("q")], "q", [], summarize)

    assert "http" not in report
    assert stats["removed"] == 3
    assert summarize.corrections[1] == correction_note([])
    assert "do not include any URLs" in summarize.corrections[1]


async def test_logs_counts_only(capsys):
    await summarize_with_guard(RESULTS, "q", [], FakeSummarizer(INVENTED, INVENTED))

    out = capsys.readouterr().out
    assert "[citation_guard]" in out
    assert "Claim" not in out and FAKE not in out and URL1 not in out


# ── low citation coverage ─────────────────────────────────────────────────────

UNCITED = "## Findings\n- Claim one.\n- Claim two.\n- Claim three.\n"
LOW = f"## Findings\n- Claim one [source]({URL1})\n- Claim two.\n- Claim three.\n"  # 1/3 cited
HALF = f"## Findings\n- Claim one [source]({URL1})\n- Claim two.\n"  # exactly 50%


def test_citation_coverage():
    assert citation_coverage(CLEAN) == 1.0
    assert citation_coverage(LOW) == pytest.approx(1 / 3)
    assert citation_coverage(UNCITED) == 0.0
    assert citation_coverage("") == 0.0


def test_report_units_split_bullets_and_sentences_skip_headings():
    assert report_units("# Title\n\nFirst sentence. Second one.\n- A bullet\n---\n") == [
        "First sentence.",
        "Second one.",
        "A bullet",
    ]


@pytest.mark.parametrize("first", [UNCITED, LOW], ids=["zero_citations", "below_50pct"])
async def test_low_coverage_triggers_retry_with_citation_note(first):
    summarize = FakeSummarizer(first, CLEAN)

    report, stats = await summarize_with_guard(RESULTS, "q", [], summarize)

    assert report == CLEAN
    assert stats["retried"] is True
    assert stats["low_coverage_retry"] is True
    assert stats["invented_before_retry"] == 0
    note = summarize.corrections[1]
    assert note == coverage_note([URL1, URL2])
    assert "Every factual claim" in note and URL1 in note


async def test_exactly_half_coverage_does_not_retry():
    summarize = FakeSummarizer(HALF)

    _, stats = await summarize_with_guard(RESULTS, "q", [], summarize)

    assert summarize.corrections == [None]
    assert stats["retried"] is False and stats["low_coverage_retry"] is False


async def test_no_sources_and_no_citations_does_not_retry():
    summarize = FakeSummarizer("No search results were found for this question.")

    _, stats = await summarize_with_guard([fallback_result("q")], "q", [], summarize)

    assert summarize.corrections == [None]
    assert stats["low_coverage_retry"] is False


async def test_invented_and_low_coverage_share_one_retry():
    first = f"- Claim one [x]({FAKE})\n- Claim two.\n- Claim three.\n"
    summarize = FakeSummarizer(first, CLEAN)

    report, stats = await summarize_with_guard(RESULTS, "q", [], summarize)

    assert report == CLEAN
    assert len(summarize.corrections) == 2  # one retry, not two
    note = summarize.corrections[1]
    assert correction_note([URL1, URL2]) in note and coverage_note([URL1, URL2]) in note
    assert stats == {
        "citations_checked": 3,
        "invented_before_retry": 1,
        "retried": True,
        "low_coverage_retry": True,
        "removed": 0,
    }


async def test_low_coverage_retry_that_invents_is_still_stripped():
    summarize = FakeSummarizer(UNCITED, INVENTED)

    report, stats = await summarize_with_guard(RESULTS, "q", [], summarize)

    assert FAKE not in report
    assert stats["low_coverage_retry"] is True and stats["removed"] == 2
    assert len(summarize.corrections) == 2


# ── URLs outside markdown links (regressions found by the eval) ───────────────

PAREN_URL = "https://www.cell.com/trends/fulltext/S0968-0004(20)30150-X?rss=yes"


def test_url_with_parentheses_is_parsed_whole_and_matches_source():
    report = f"- Base editing review [source]({PAREN_URL}).\n"
    allowed = {normalize_url(PAREN_URL)}
    assert visible_urls(report) == [PAREN_URL]
    assert find_invented(report, allowed) == []
    assert strip_invented(report, allowed) == (report, 0)


def test_link_label_repeating_an_invented_url_is_fully_removed():
    report = f"- Claim [{FAKE}]({FAKE}).\n"
    stripped, removed = strip_invented(report, {normalize_url(URL1)})
    assert stripped == "- Claim (unverified).\n"
    assert removed == 1


def test_valid_link_with_invented_url_in_label_keeps_target_only():
    report = f"- Claim [{FAKE}]({URL1}).\n"
    allowed = {normalize_url(URL1)}
    assert find_invented(report, allowed) == [FAKE]
    stripped, _ = strip_invented(report, allowed)
    assert stripped == f"- Claim [source]({URL1}).\n"


def test_bare_and_bracketed_urls_are_checked_and_stripped():
    report = f"- Claim one [{URL1}, {FAKE}].\n- Claim two {FAKE}.\n- Claim three ({URL2}).\n"
    allowed = {normalize_url(URL1), normalize_url(URL2)}

    assert visible_urls(report) == [URL1, FAKE, URL2]
    assert find_invented(report, allowed) == [FAKE]
    stripped, removed = strip_invented(report, allowed)
    assert FAKE not in stripped
    assert removed == 2
    assert stripped == f"- Claim one [{URL1}, (unverified)].\n- Claim two (unverified).\n- Claim three ({URL2}).\n"


async def test_retry_with_bare_invented_urls_is_stripped():
    summarize = FakeSummarizer(INVENTED, f"- Claim one [source]({URL1})\n- Claim two [{FAKE}].\n")

    report, stats = await summarize_with_guard(RESULTS, "q", [], summarize)

    assert FAKE not in report
    assert "[(unverified)]" in report
    assert stats["removed"] == 1


def test_correction_notes_require_markdown_link_format():
    for note in (correction_note([URL1]), coverage_note([URL1])):
        assert "[source](URL)" in note
        assert "Never write a bare URL" in note
