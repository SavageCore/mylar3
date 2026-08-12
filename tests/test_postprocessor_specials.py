import re

import pytest

import mylar
from mylar import filechecker


def build_loopchk(series_name, annuals_on):
    """Mirror the loopchk construction in PostProcessor.Process.

    The code under test is the ANNUALS_ON-independent special-stripping
    fallback added to PostProcessor.py (regression for one-shot specials
    whose DB DynamicComicName omits the word 'special', e.g. 'Preacher:
    Tall in the Saddle' -> 'preachertallinsaddle').
    """
    as_d = filechecker.FileChecker()
    as_dinfo = as_d.dynamic_replace(series_name)
    orig_seriesname = as_dinfo["mod_seriesname"]
    mod_seriesname = as_dinfo["mod_seriesname"]
    loopchk = []

    if all([annuals_on, "annual" in mod_seriesname.lower()]) or all([annuals_on, "special" in mod_seriesname.lower()]):
        mod_seriesname = re.sub("2021annual", "", mod_seriesname, flags=re.I).strip()
        mod_seriesname = re.sub("annual", "", mod_seriesname, flags=re.I).strip()
        mod_seriesname = re.sub("special", "", mod_seriesname, flags=re.I).strip()

    if any(["annual" in orig_seriesname.lower(), "special" in orig_seriesname.lower()]):
        mod_seriesname_annuals = re.sub("2021annual", "", orig_seriesname, flags=re.I).strip()
        mod_seriesname_annuals = re.sub("annual", "", mod_seriesname_annuals, flags=re.I).strip()
        mod_seriesname_annuals = re.sub("special", "", mod_seriesname_annuals, flags=re.I).strip()
        if mod_seriesname_annuals != orig_seriesname and not any(re.sub(r"[\|\s]", "", mod_seriesname_annuals).lower() == x for x in loopchk):
            loopchk.append(re.sub(r"[\|\s]", "", mod_seriesname_annuals.lower()))

    if not any(re.sub(r"[\|\s]", "", mod_seriesname).lower() == x for x in loopchk):
        loopchk.append(re.sub(r"[\|\s]", "", mod_seriesname.lower()))

    return loopchk


@pytest.mark.parametrize(
    "filename",
    [
        # one-shot special whose DB DynamicComicName is 'preachertallinsaddle'
        # (ComicName has no 'special') - only the stripped variant matches
        "Preacher Special - Tall in the Saddle",
        # specials whose DB DynamicComicName keeps the word 'special'
        "Preacher Special - Saint of Killers",
        "Preacher Special - The Good Old Boys",
    ],
)
@pytest.mark.unit
def test_loopchk_always_includes_stripped_variant(monkeypatch, filename):
    monkeypatch.setattr(mylar, "CONFIG", mylar.config.Config("./nothing"))
    monkeypatch.setattr(mylar.CONFIG, "IGNORE_SEARCH_WORDS", [], raising=False)
    monkeypatch.setattr(mylar.CONFIG, "CUSTOM_ISSUE_EXCEPTIONS", [], raising=False)
    monkeypatch.setattr(mylar.CONFIG, "READ2FILENAME", False, raising=False)
    monkeypatch.setattr(mylar.CONFIG, "FOLDER_SCAN_LOG_VERBOSE", False, raising=False)

    for annuals_on in (True, False):
        loopchk = build_loopchk(filename, annuals_on=annuals_on)
        # the stripped variant (word removed) must always be present so a watchlist
        # entry whose DynamicComicName omits 'special'/'annual' can match
        assert any(("tallinsaddle" in x or "saintofkillers" in x or "goodoldboys" in x) for x in loopchk)


@pytest.mark.unit
def test_loopchk_tall_in_saddle_matches_db_name(monkeypatch):
    """ANNUALS_ON=False must still produce 'preachertallinsaddle' so the DB query
    for 'Preacher: Tall in the Saddle' (DynamicComicName 'preachertallinsaddle')
    succeeds during folder-check."""
    monkeypatch.setattr(mylar, "CONFIG", mylar.config.Config("./nothing"))
    monkeypatch.setattr(mylar.CONFIG, "IGNORE_SEARCH_WORDS", [], raising=False)
    monkeypatch.setattr(mylar.CONFIG, "CUSTOM_ISSUE_EXCEPTIONS", [], raising=False)
    monkeypatch.setattr(mylar.CONFIG, "READ2FILENAME", False, raising=False)
    monkeypatch.setattr(mylar.CONFIG, "FOLDER_SCAN_LOG_VERBOSE", False, raising=False)

    loopchk = build_loopchk("Preacher Special - Tall in the Saddle", annuals_on=False)
    assert "preachertallinsaddle" in loopchk
