"""Tests for the folder-monitor skip cache (checked_files table).

Mirrors the monkeypatch style of test_postprocessor_specials.py. The helpers
under test are PostProcessor._should_skip_cached and PostProcessor._cache_skip,
which the Folder Monitor (folder_monitor=True) uses to avoid re-logging
'Now checking: ...' for files that are unchanged on disk and whose matching
issue is still not in a Wanted/Snatched state.
"""
import os

import pytest

import mylar
from mylar import PostProcessor


class FakeRow:
    """Minimal stand-in for a sqlite3.Row with both dict and tuple access."""

    def __init__(self, **kwargs):
        self._d = kwargs
        self._t = list(kwargs.values())

    def __getitem__(self, key):
        if isinstance(key, int):
            return self._t[key]
        return self._d[key]


class FakeDB:
    """In-memory fake of db.DBConnection used by the helpers under test.

    Supports:
      - selectone(query, args): returns an object with a fetchone() method
        whose return value is driven by the canned selectone_results queue.
      - action(query, args): records the call; if the query starts with
        DELETE, records a deletion event.
      - upsert(table, valueDict, keyDict): records the call.
    """

    def __init__(self):
        self.selectone_results = []
        self.actions = []
        self.upserts = []

    def selectone(self, query, args=None):
        class _Canned:
            def __init__(self, result):
                self._result = result

            def fetchone(self):
                return self._result

        if self.selectone_results:
            result = self.selectone_results.pop(0)
        else:
            result = None
        return _Canned(result)

    def action(self, query, args=None):
        self.actions.append((query, args))

    def upsert(self, table, valueDict, keyDict):
        self.upserts.append((table, valueDict, keyDict))


def _row(**kwargs):
    return FakeRow(**kwargs)


def _make_pp(monkeypatch, folder_monitor=True):
    monkeypatch.setattr(mylar, "CONFIG", mylar.config.Config("./nothing"))
    monkeypatch.setattr(mylar.CONFIG, "FILE_OPTS", "move", raising=False)
    monkeypatch.setattr(mylar.CONFIG, "IGNORE_SEARCH_WORDS", [], raising=False)
    monkeypatch.setattr(mylar, "APILOCK", False, raising=False)
    monkeypatch.setattr(mylar.CONFIG, "FOLDER_MONITOR_CACHE", True, raising=False)
    monkeypatch.setattr(mylar.CONFIG, "ANNUALS_ON", False, raising=False)
    pp = PostProcessor.PostProcessor("Manual Run", "/tmp", folder_monitor=folder_monitor)
    return pp


def _stat(path, mtime=1000, size=100):
    class _S:
        st_mtime = mtime
        st_size = size

    return _S()


def _mock_stat_for(target, mtime=1000, size=100, missing=False):
    """Return a function that fakes os.stat() for `target` but delegates every
    other path to the real os.stat() (pytest internals use pathlib/os.stat)."""
    real_stat = os.stat

    def _stat_mock(path, *args, **kwargs):
        if os.fspath(path) == target:
            if missing:
                raise FileNotFoundError(target)
            return _stat(path, mtime=mtime, size=size)
        return real_stat(path, *args, **kwargs)

    return _stat_mock


@pytest.mark.unit
def test_should_skip_cached_hit_status_unchanged(monkeypatch):
    pp = _make_pp(monkeypatch)
    monkeypatch.setattr(os, "stat", _mock_stat_for("/tmp/foo.cbr"))
    myDB = FakeDB()
    # cache row: file unchanged, issue previously observed as Downloaded
    myDB.selectone_results = [
        _row(observed_status="Downloaded", IssueID="i1",
             Int_IssueNumber=5, mtime=1000, size=100),
        # current status lookup
        _row(Status="Downloaded"),
    ]
    skip, reason = pp._should_skip_cached("/tmp/foo.cbr", _row(ComicID="5516"), myDB)
    assert skip is True
    assert reason == "cache-hit-status-unchanged"
    # no invalidations / fallthrough writes happened
    assert all(not q.startswith("DELETE") for q, _ in myDB.actions)


@pytest.mark.unit
def test_should_skip_cached_status_flipped_to_wanted(monkeypatch):
    pp = _make_pp(monkeypatch)
    monkeypatch.setattr(os, "stat", _mock_stat_for("/tmp/foo.cbr"))
    myDB = FakeDB()
    myDB.selectone_results = [
        _row(observed_status="Downloaded", IssueID="i1",
             Int_IssueNumber=5, mtime=1000, size=100),
        # current status now Wanted -> must invalidate and fall through
        _row(Status="Wanted"),
    ]
    skip, reason = pp._should_skip_cached("/tmp/foo.cbr", _row(ComicID="5516"), myDB)
    assert skip is False
    assert reason == "status-changed"
    assert myDB.actions == [("DELETE FROM checked_files WHERE file_path=? AND ComicID=?",
                             ["/tmp/foo.cbr", "5516"])]


@pytest.mark.unit
def test_should_skip_cached_file_mtime_changed(monkeypatch):
    pp = _make_pp(monkeypatch)
    monkeypatch.setattr(os, "stat", _mock_stat_for("/tmp/foo.cbr", mtime=9999))
    myDB = FakeDB()
    myDB.selectone_results = [
        _row(observed_status="Downloaded", IssueID="i1",
             Int_IssueNumber=5, mtime=1000, size=100),
    ]
    skip, reason = pp._should_skip_cached("/tmp/foo.cbr", _row(ComicID="5516"), myDB)
    assert skip is False
    assert reason == "file-changed"
    assert myDB.actions == [("DELETE FROM checked_files WHERE file_path=? AND ComicID=?",
                             ["/tmp/foo.cbr", "5516"])]


@pytest.mark.unit
def test_should_skip_cached_file_gone(monkeypatch):
    pp = _make_pp(monkeypatch)

    monkeypatch.setattr(os, "stat", _mock_stat_for("/tmp/gone.cbr", missing=True))
    myDB = FakeDB()
    skip, reason = pp._should_skip_cached("/tmp/gone.cbr", _row(ComicID="5516"), myDB)
    assert skip is False
    assert reason == "file-gone"
    assert myDB.actions == [("DELETE FROM checked_files WHERE file_path=? AND ComicID=?",
                             ["/tmp/gone.cbr", "5516"])]


@pytest.mark.unit
def test_should_skip_cached_disabled_via_config(monkeypatch):
    pp = _make_pp(monkeypatch)
    monkeypatch.setattr(mylar.CONFIG, "FOLDER_MONITOR_CACHE", False, raising=False)
    myDB = FakeDB()
    # If disabled, no DB reads should happen at all.
    skip, reason = pp._should_skip_cached("/tmp/foo.cbr", _row(ComicID="5516"), myDB)
    assert skip is False
    assert reason == "disabled"
    assert myDB.selectone_results == []
    assert myDB.actions == []
    assert myDB.upserts == []


@pytest.mark.unit
def test_should_skip_cached_disabled_non_folder_monitor(monkeypatch):
    # A non-folder-monitor PostProcessor never consults the cache.
    pp = _make_pp(monkeypatch, folder_monitor=False)
    myDB = FakeDB()
    skip, reason = pp._should_skip_cached("/tmp/foo.cbr", _row(ComicID="5516"), myDB)
    assert skip is False
    assert reason == "disabled"
    assert myDB.actions == []


@pytest.mark.unit
def test_should_skip_cached_no_cache_row(monkeypatch):
    pp = _make_pp(monkeypatch)
    monkeypatch.setattr(os, "stat", _mock_stat_for("/tmp/foo.cbr"))
    myDB = FakeDB()
    myDB.selectone_results = [None]  # no checked_files row
    skip, reason = pp._should_skip_cached("/tmp/foo.cbr", _row(ComicID="5516"), myDB)
    assert skip is False
    assert reason == "no-cache"
    assert myDB.actions == []


@pytest.mark.unit
def test_should_skip_cached_issue_unlocatable_now(monkeypatch):
    """If the file fingerprint matches but the issue row is now missing (and the
    cached decision was NOT 'Paused-Ended'), be conservative and re-process."""
    pp = _make_pp(monkeypatch)
    monkeypatch.setattr(os, "stat", _mock_stat_for("/tmp/foo.cbr"))
    myDB = FakeDB()
    myDB.selectone_results = [
        _row(observed_status="Downloaded", IssueID="i1",
             Int_IssueNumber=5, mtime=1000, size=100),
        None,  # issues lookup returns nothing
    ]
    skip, reason = pp._should_skip_cached("/tmp/foo.cbr", _row(ComicID="5516"), myDB)
    assert skip is False
    assert reason == "issue-unlocatable"
    assert myDB.actions == [("DELETE FROM checked_files WHERE file_path=? AND ComicID=?",
                             ["/tmp/foo.cbr", "5516"])]


@pytest.mark.unit
def test_should_skip_cached_paused_ended_still_missing(monkeypatch):
    """'Paused-Ended' sentinel caches a 'no issue row' decision. If the issue is
    STILL absent on re-check, skip it (it remains un-actionable)."""
    pp = _make_pp(monkeypatch)
    monkeypatch.setattr(os, "stat", _mock_stat_for("/tmp/foo.cbr"))
    myDB = FakeDB()
    myDB.selectone_results = [
        _row(observed_status="Paused-Ended", IssueID=None,
             Int_IssueNumber=5, mtime=1000, size=100),
        None,  # issues lookup returns nothing
    ]
    skip, reason = pp._should_skip_cached("/tmp/foo.cbr", _row(ComicID="5516"), myDB)
    assert skip is True
    assert reason == "cache-hit-issue-still-missing"


@pytest.mark.unit
def test_cache_skip_writes_upsert(monkeypatch):
    pp = _make_pp(monkeypatch)
    monkeypatch.setattr(os, "stat", _mock_stat_for("/tmp/foo.cbr", mtime=1234, size=5678))
    myDB = FakeDB()
    myDB.selectone_results = [_row(IssueID="issue-9")]
    pp._cache_skip("/tmp/foo.cbr", _row(ComicID="5516"), 5, "Downloaded", myDB)
    assert len(myDB.upserts) == 1
    table, valueDict, keyDict = myDB.upserts[0]
    assert table == "checked_files"
    assert valueDict["mtime"] == 1234
    assert valueDict["size"] == 5678
    assert valueDict["Int_IssueNumber"] == 5
    assert valueDict["observed_status"] == "Downloaded"
    assert valueDict["IssueID"] == "issue-9"
    assert keyDict == {"file_path": "/tmp/foo.cbr", "ComicID": "5516"}


@pytest.mark.unit
def test_cache_skip_disabled_when_folder_monitor_off(monkeypatch):
    pp = _make_pp(monkeypatch, folder_monitor=False)
    monkeypatch.setattr(os, "stat", _mock_stat_for("/tmp/foo.cbr"))
    myDB = FakeDB()
    pp._cache_skip("/tmp/foo.cbr", _row(ComicID="5516"), 5, "Downloaded", myDB)
    assert myDB.upserts == []
    assert myDB.selectone_results == []


@pytest.mark.unit
def test_cache_skip_skips_when_issue_number_missing(monkeypatch):
    pp = _make_pp(monkeypatch)
    monkeypatch.setattr(os, "stat", _mock_stat_for("/tmp/foo.cbr"))
    myDB = FakeDB()
    pp._cache_skip("/tmp/foo.cbr", _row(ComicID="5516"), None, "Downloaded", myDB)
    assert myDB.upserts == []
    assert myDB.selectone_results == []


@pytest.mark.unit
def test_cache_skip_no_issueid_ok(monkeypatch):
    """_cache_skip still writes a row even when no IssueID is found."""
    pp = _make_pp(monkeypatch)
    monkeypatch.setattr(os, "stat", _mock_stat_for("/tmp/foo.cbr"))
    myDB = FakeDB()
    myDB.selectone_results = [None]  # no issue row found
    pp._cache_skip("/tmp/foo.cbr", _row(ComicID="5516"), 5, "Downloaded", myDB)
    assert len(myDB.upserts) == 1
    assert myDB.upserts[0][1]["IssueID"] is None
