import pytest

from agents.citation_guard import (
    cited_ids,
    citation_coverage,
    correction_note,
    coverage_note,
    find_invalid_ids,
    find_invented,
    normalize_url,
    number_sources,
    report_units,
    resolve_ids,
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


async def test_raw_invented_url_triggers_retry_with_id_note():
    summarize = FakeSummarizer(INVENTED, CLEAN)

    report, stats = await summarize_with_guard(RESULTS, "q", [], summarize)

    assert report == CLEAN
    assert stats == {"citations_checked": 4, "invented_before_retry": 1, "retried": True, "low_coverage_retry": False, "removed": 0}
    note = summarize.corrections[1]
    assert note == correction_note(2)
    assert "http" not in note  # the retry prompt carries no URLs either


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
    assert summarize.corrections[1] == correction_note(0)
    assert "no sources are available" in summarize.corrections[1]


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
    assert summarize.corrections[1] == coverage_note()


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
    assert note == correction_note(2) + "\n\n" + coverage_note()
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




# ── source-ID citations ───────────────────────────────────────────────────────

SOURCES = number_sources(RESULTS)
LINK1, LINK2 = f"[example.com]({URL1})", f"[example.com]({URL2})"
ID_CLEAN = "## Findings\n- Claim one [S1].\n- Claim two [S2].\n"


def test_number_sources_skips_fallbacks_and_shares_ids_for_repeated_urls():
    repeat = make_result("query a", 1).model_copy(update={"query": "query c", "search_result": "other summary"})
    sources = number_sources([*RESULTS, repeat])
    assert list(sources) == ["S1", "S2"]
    assert [r.search_result for r in sources["S1"]] == ["content for query a #1", "other summary"]


def test_ids_map_to_domain_links():
    report, removed = resolve_ids(ID_CLEAN, SOURCES)
    assert report == f"## Findings\n- Claim one {LINK1}.\n- Claim two {LINK2}.\n"
    assert removed == 0
    assert citation_coverage(report) == 1.0


@pytest.mark.parametrize("cite", ["[S1][S2]", "[S1] [S2]", "[S1, S2]", "[S1; S2]", "[S1][S2][S1]"])
def test_multiple_ids_map_to_one_link_each(cite):
    report, _ = resolve_ids(f"- Claim {cite}.\n", SOURCES)
    assert report == f"- Claim {LINK1} {LINK2}.\n"
    assert cited_ids(f"- Claim {cite}.") == ["S1", "S2"]


def test_unknown_id_is_removed_and_marked_unverified():
    draft = "- Claim one [S1][S9].\n- Claim two [S7].\n- Claim three [S8, S9].\n"
    assert find_invalid_ids(draft, SOURCES) == ["S9", "S7", "S8"]
    report, removed = resolve_ids(draft, SOURCES)
    assert report == f"- Claim one {LINK1} (unverified).\n- Claim two (unverified).\n- Claim three (unverified).\n"
    assert removed == 4


def test_id_used_as_link_label_is_not_an_id_citation():
    draft = f"- Claim [S1]({URL1}).\n"
    assert cited_ids(draft) == []
    assert resolve_ids(draft, SOURCES) == (draft, 0)


async def test_id_report_passes_without_retry():
    summarize = FakeSummarizer(ID_CLEAN)

    report, stats = await summarize_with_guard(RESULTS, "q", [], summarize)

    assert report == f"## Findings\n- Claim one {LINK1}.\n- Claim two {LINK2}.\n"
    assert summarize.corrections == [None]
    assert stats == {"citations_checked": 2, "invented_before_retry": 0, "retried": False, "low_coverage_retry": False, "removed": 0}


async def test_unknown_id_triggers_retry_naming_it():
    summarize = FakeSummarizer("- Claim one [S1].\n- Claim two [S5].\n", ID_CLEAN)

    report, stats = await summarize_with_guard(RESULTS, "q", [], summarize)

    assert report == f"## Findings\n- Claim one {LINK1}.\n- Claim two {LINK2}.\n"
    assert stats["invented_before_retry"] == 1 and stats["retried"] is True and stats["removed"] == 0
    note = summarize.corrections[1]
    assert note == correction_note(2, ["S5"])
    assert "(S5)" in note and "Only S1 to S2 exist" in note
    assert "remove claims no listed source supports" in note.lower()


async def test_unknown_id_after_retry_is_marked_unverified():
    draft = "- Claim one [S1].\n- Claim two [S5].\n"
    summarize = FakeSummarizer(draft, draft)

    report, stats = await summarize_with_guard(RESULTS, "q", [], summarize)

    assert report == f"- Claim one {LINK1}.\n- Claim two (unverified).\n"
    assert len(summarize.corrections) == 2  # exactly one retry
    assert stats["removed"] == 1


async def test_ids_with_no_sources_are_invented():
    summarize = FakeSummarizer("- Claim [S1].\n", "- Claim [S1].\n")

    report, stats = await summarize_with_guard([fallback_result("q")], "q", [], summarize)

    assert report == "- Claim (unverified).\n"
    assert summarize.corrections[1] == correction_note(0)
    assert stats["removed"] == 1


async def test_raw_urls_alongside_ids_are_still_checked():
    """Backstop: a raw invented URL in an ID-cited report is retried, then stripped."""
    draft = f"- Claim one [S1].\n- Claim two [Made Up]({FAKE}).\n- Claim three {FAKE}.\n"
    summarize = FakeSummarizer(draft, draft)

    report, stats = await summarize_with_guard(RESULTS, "q", [], summarize)

    assert FAKE not in report
    assert report == f"- Claim one {LINK1}.\n- Claim two (unverified).\n- Claim three (unverified).\n"
    assert stats["invented_before_retry"] == 1 and stats["removed"] == 2


async def test_low_coverage_counts_resolved_ids_and_note_allows_removal():
    summarize = FakeSummarizer("- Claim one [S1].\n- Claim two.\n- Claim three.\n", ID_CLEAN)

    _, stats = await summarize_with_guard(RESULTS, "q", [], summarize)

    assert stats["low_coverage_retry"] is True
    note = summarize.corrections[1]
    assert note == coverage_note()
    assert "Cite a source ID for each claim, and remove claims no listed source supports" in note


def test_correction_notes_ask_for_ids_never_urls():
    for note in (correction_note(3), correction_note(3, ["S9"]), coverage_note()):
        assert "[S1]" in note
        assert "Never write URLs" in note
        assert "http" not in note
    # A coverage retry must always allow removing claims, never only ask for more citations.
    assert "remove claims" in coverage_note()
