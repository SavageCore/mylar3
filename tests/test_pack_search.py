import re

import pytest

import mylar
from mylar import filechecker, rsscheck


@pytest.mark.parametrize(
    "title,expected_issues",
    [
        ("Transmetropolitan #1-60 (1997-2002)", "1-60"),
        ("Transmetropolitan (1997) #1-60 ", "1-60"),
        ("Saga #001-060 (2012-2020)", "001-060"),
        ("The Walking Dead #1-193 + Extras (2003-2019)", "1-193"),
        ("Transmetropolitan 1 - 60 (1997-2002)", "1 - 60"),
        # negatives: ordinary single-issue releases must not be detected as packs
        ("Batman #700 (2010)", None),
        ("Batman 2010-01-01 (2010)", None),
        # known misses - not currently detected, documented rather than fixed
        ("Transmetropolitan #01 - #60 (1997-2002)", None),
        ("Transmetropolitan v01-v10 (1997-2002)", None),
    ],
)
@pytest.mark.unit
def test_ddlrss_pack_detect(title, expected_issues):
    result = rsscheck.ddlrss_pack_detect(title, "http://example.com/link")

    if expected_issues is None:
        assert result is None
    else:
        assert result is not None
        assert result["pack"] is True
        assert result["issues"] == expected_issues


@pytest.mark.unit
def test_pack_title_strips_to_matchable_series(monkeypatch):
    monkeypatch.setattr(mylar, "CONFIG", mylar.config.Config("./nothing"))
    monkeypatch.setattr(mylar.CONFIG, "IGNORE_SEARCH_WORDS", [], raising=False)
    monkeypatch.setattr(mylar.CONFIG, "CUSTOM_ISSUE_EXCEPTIONS", [], raising=False)
    monkeypatch.setattr(mylar.CONFIG, "READ2FILENAME", False, raising=False)
    monkeypatch.setattr(mylar.CONFIG, "FOLDER_SCAN_LOG_VERBOSE", False, raising=False)
    monkeypatch.setattr(mylar.CONFIG, "ANNUALS_ON", False, raising=False)

    title = "Transmetropolitan #1-60 (1997-2002)"
    packchk = rsscheck.ddlrss_pack_detect(title + " ", "http://example.com/link")
    assert packchk is not None

    # mirrors the cleanup done in search_filer._process_entry for non-DDL packs
    stripped_title = re.sub(r'\(\d{4}(?:-\d{4})?\)', '', packchk["title"]).strip()
    stripped_title = re.sub(r'#\s*$', '', stripped_title).strip()
    assert stripped_title == "Transmetropolitan"

    parsed = filechecker.FileChecker(
        file=stripped_title, watchcomic="Transmetropolitan"
    ).listFiles()

    parsed_comic = {
        "booktype": "issue",
        "comicfilename": title,
        "series_name": parsed["series_name"],
        "series_name_decoded": parsed["series_name"],
        "issueid": None,
        "dynamic_name": parsed["series_name"],
        "issues": packchk["issues"],
        "series_volume": None,
        "alt_series": None,
        "alt_issue": None,
        "issue_year": parsed["issue_year"],
        "issue_number": None,
        "scangroup": None,
        "reading_order": None,
        "sub": None,
        "comiclocation": None,
        "parse_status": "success",
    }

    matched = filechecker.FileChecker(watchcomic="Transmetropolitan").matchIT(parsed_comic)
    assert matched["process_status"] == "match"
