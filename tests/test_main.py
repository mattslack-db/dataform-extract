from dataform_extract.cli import Args
from dataform_extract.__main__ import run, Summary
import dataform_extract.__main__ as m
from dataform_extract.auth import AuthError
from dataform_extract.api import ApiError

def make_args(tmp_path, **over):
    base = dict(repo="projects/p/locations/us/repositories/r", commitish="main",
                workspace=None, out=str(tmp_path), path_filter=None,
                include_assertions=False, include_operations=True)
    base.update(over)
    return Args(**base)

class FakeClient:
    def __init__(self, actions, token, **kw):
        self.actions = actions
    def create_compilation_result(self, repo, *, commitish=None, workspace=None):
        return "cr/1"
    def query_actions(self, name):
        return self.actions

def _run(tmp_path, actions, **over):
    return run(make_args(tmp_path, **over),
               token_getter=lambda: "tok",
               client_factory=lambda token: FakeClient(actions, token))

def test_writes_table_and_skips_declaration(tmp_path):
    actions = [
        {"filePath": "definitions/o.sqlx", "target": {"database": "p", "schema": "s", "name": "o"},
         "relation": {"relationType": "TABLE", "selectQuery": "SELECT 1"}},
        {"filePath": "definitions/d.sqlx", "target": {"database": "p", "schema": "s", "name": "d"},
         "declaration": {}},
    ]
    summary = _run(tmp_path, actions)
    assert summary == Summary(written=1, skipped=1, warnings=0, incremental=0)
    assert (tmp_path / "definitions/o.sql").read_text() == \
        "CREATE OR REPLACE TABLE `p.s.o` AS\nSELECT 1;\n"

def test_path_filter_excludes_non_matching(tmp_path):
    actions = [
        {"filePath": "definitions/marts/a.sqlx", "target": {"database": "p", "schema": "s", "name": "a"},
         "relation": {"relationType": "VIEW", "selectQuery": "SELECT 1"}},
        {"filePath": "definitions/staging/b.sqlx", "target": {"database": "p", "schema": "s", "name": "b"},
         "relation": {"relationType": "VIEW", "selectQuery": "SELECT 2"}},
    ]
    summary = _run(tmp_path, actions, path_filter="definitions/marts")
    assert summary.written == 1
    assert (tmp_path / "definitions/marts/a.sql").exists()
    assert not (tmp_path / "definitions/staging/b.sql").exists()

def test_malformed_relation_counts_as_warning(tmp_path):
    actions = [
        {"filePath": "definitions/bad.sqlx", "target": {"database": "p", "schema": "s", "name": "bad"},
         "relation": {"relationType": "TABLE"}},
    ]
    summary = _run(tmp_path, actions)
    assert summary == Summary(written=0, skipped=0, warnings=1, incremental=0)

def test_incremental_counted(tmp_path):
    actions = [
        {"filePath": "definitions/i.sqlx", "target": {"database": "p", "schema": "s", "name": "i"},
         "relation": {"relationType": "INCREMENTAL_TABLE", "selectQuery": "SELECT 1"}},
    ]
    summary = _run(tmp_path, actions)
    assert summary.written == 1 and summary.incremental == 1

def test_unsafe_path_error_counts_as_warning(tmp_path):
    actions = [
        {"filePath": "../escape.sqlx", "target": {"database": "p", "schema": "s", "name": "escape"},
         "relation": {"relationType": "TABLE", "selectQuery": "SELECT 1"}},
    ]
    summary = _run(tmp_path, actions)
    assert summary == Summary(written=0, skipped=0, warnings=1, incremental=0)

def test_main_success_returns_0_and_prints_summary(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(m, "run", lambda args: Summary(written=5, skipped=1, warnings=0, incremental=2))
    args = [
        "--repo", "projects/p/locations/us/repositories/r",
        "--commitish", "main",
        "--out", str(tmp_path)
    ]
    ret = m.main(args)
    assert ret == 0
    captured = capsys.readouterr()
    assert "Wrote 5 .sql file(s)" in captured.out
    assert "1 skipped" in captured.out
    assert "0 warning(s)" in captured.out
    assert "2 incremental" in captured.out

def test_main_auth_error_returns_2(tmp_path, monkeypatch, capsys):
    def fake_run(args):
        raise AuthError("auth failed")
    monkeypatch.setattr(m, "run", fake_run)
    args = [
        "--repo", "projects/p/locations/us/repositories/r",
        "--commitish", "main",
        "--out", str(tmp_path)
    ]
    ret = m.main(args)
    assert ret == 2
    captured = capsys.readouterr()
    assert "ERROR: auth failed" in captured.err

def test_main_api_error_returns_1(tmp_path, monkeypatch, capsys):
    def fake_run(args):
        raise ApiError("api failed")
    monkeypatch.setattr(m, "run", fake_run)
    args = [
        "--repo", "projects/p/locations/us/repositories/r",
        "--commitish", "main",
        "--out", str(tmp_path)
    ]
    ret = m.main(args)
    assert ret == 1
    captured = capsys.readouterr()
    assert "ERROR: api failed" in captured.err
