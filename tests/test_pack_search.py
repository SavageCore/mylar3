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


def test_whole_series_pack_detect_bare_series_name():
    """A bare 'Watchmen (1986)' style title should be detected as a whole-series
    pack in the name-only pack pass."""
    from mylar import search_filer

    sf = search_filer.search_check()

    class FakeDB(object):
        def __init__(self):
            self.data = [
                {'Int_IssueNumber': 1000},
                {'Int_IssueNumber': 2000},
                {'Int_IssueNumber': 12000},
            ]

        def select(self, query, args):
            assert 'Wanted' in query
            return self.data

    import mylar
    mylar.db.DBConnection = lambda: FakeDB()

    result = sf._whole_series_pack_detect(
        'Watchmen (1986)', 'Watchmen', '1986', '3622'
    )
    assert result is not None
    assert result['title'] == 'Watchmen (1986)'
    assert result['issues'] == '1-12'

    # a single-issue title must not be treated as a whole-series pack
    result = sf._whole_series_pack_detect(
        'Watchmen 12 (1987)', 'Watchmen', '1986', '3622'
    )
    assert result is None


def test_whole_series_pack_detect_wrong_series():
    from mylar import search_filer

    sf = search_filer.search_check()

    result = sf._whole_series_pack_detect(
        'Before Watchmen - Comedian (2012)', 'Watchmen', '1986', '3622'
    )
    assert result is None


def test_ddlrss_pack_detect_no_hash_no_space_after_dash():
    """Titles like 'Preacher 1-66 ...' have no '#' and no space after the dash."""
    result = rsscheck.ddlrss_pack_detect(
        'Preacher 1-66 (complete, noAds) (theProletariat-DCP)', 'http://example.com'
    )
    assert result is not None
    assert result['pack'] is True


def test_ddlrss_pack_detect_preacher_family():
    """Preacher-style no-space dash ranges must detect as packs."""
    for t, exp in [
        ('Preacher 1-66 (complete, noAds) (theProletariat-DCP)', '1-66'),
        ('Preacher 1 - 66 (complete)', '1 - 66'),
        ('Preacher #1-66 (complete)', '1-66'),
    ]:
        result = rsscheck.ddlrss_pack_detect(t, 'http://example.com')
        assert result is not None, t
        assert result['pack'] is True, t
        assert result['issues'] == exp, (t, result['issues'])


def test_whole_series_pack_detect_franchise_spinoff():
    """A franchise pack like 'Preacher (001-066 + Books 01-06 + Specials)'
    should match when searching a spin-off series (e.g. 'Preacher Special:
    Saint of Killers') via the root series name."""
    from mylar import search_filer

    sf = search_filer.search_check()

    class FakeDB(object):
        def __init__(self):
            self.data = [
                {'Int_IssueNumber': 1000},
                {'Int_IssueNumber': 2000},
                {'Int_IssueNumber': 3000},
                {'Int_IssueNumber': 4000},
            ]

        def select(self, query, args):
            assert 'Wanted' in query
            return self.data

    import mylar
    mylar.db.DBConnection = lambda: FakeDB()

    result = sf._whole_series_pack_detect(
        'Preacher (001-066 + Books 01-06 + Specials) (1995-2014)',
        'Preacher Special: Saint of Killers',
        '1996',
        '5757',
    )
    assert result is not None
    assert result['issues'] == '1-4'
    assert result['title'] == 'Preacher (1996)'


def test_gen_altnames_franchise_root_fallback(monkeypatch):
    """Spin-off series searches should add the root series name as a fallback
    search so franchise packs surface."""
    import mylar
    from mylar import search

    searchlist = search.gen_altnames(
        'Preacher Special: Saint of Killers', None, None, None
    )
    names = [x['ComicName'] for x in searchlist]
    assert 'Preacher Special: Saint of Killers' in names
    assert 'Preacher' in names
