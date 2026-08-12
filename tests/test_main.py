from dataform_extract.cli import Args
from dataform_extract.__main__ import run, Summary

def make_args(tmp_path, **over):
    base = dict(repo="projects/p/locations/us/repositories/r", commitish="main",
                workspace=None, out=str(tmp_path), path_filter=None,
                include_assertions=False, include_operations=True)
    base.update(over)
    return Args(**base)

class FakeClient:
    def __init__(self, token, **kw):
        self.actions = FakeClient.ACTIONS
    def create_compilation_result(self, repo, *, commitish=None, workspace=None):
        return "cr/1"
    def query_actions(self, name):
        return self.actions

def _run(tmp_path, actions, **over):
    FakeClient.ACTIONS = actions
    return run(make_args(tmp_path, **over),
               token_getter=lambda: "tok", client_factory=FakeClient)

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
