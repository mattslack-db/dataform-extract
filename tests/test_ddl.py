import pytest
from dataform_extract import ddl

TARGET = {"database": "proj", "schema": "ds", "name": "orders"}

def test_table_with_pre_and_post_ops():
    action = {
        "filePath": "definitions/orders.sqlx",
        "target": TARGET,
        "relation": {
            "relationType": "TABLE",
            "selectQuery": "SELECT 1 AS x",
            "preOperations": ["DELETE FROM `proj.ds.tmp` WHERE 1=1"],
            "postOperations": ["GRANT SELECT ON `proj.ds.orders` TO 'x'"],
        },
    }
    assert ddl.reconstruct(action) == (
        "DELETE FROM `proj.ds.tmp` WHERE 1=1;\n\n"
        "CREATE OR REPLACE TABLE `proj.ds.orders` AS\n"
        "SELECT 1 AS x;\n\n"
        "GRANT SELECT ON `proj.ds.orders` TO 'x';"
    )

def test_view():
    action = {"target": TARGET, "relation": {"relationType": "VIEW", "selectQuery": "SELECT 2"}}
    assert ddl.reconstruct(action) == "CREATE OR REPLACE VIEW `proj.ds.orders` AS\nSELECT 2;"

def test_materialized_view_uses_create_table():
    action = {"target": TARGET,
              "relation": {"relationType": "MATERIALIZED_VIEW", "selectQuery": "SELECT 3"}}
    assert ddl.reconstruct(action) == "CREATE OR REPLACE TABLE `proj.ds.orders` AS\nSELECT 3;"

def test_incremental_emits_full_refresh_plus_comment():
    action = {
        "target": TARGET,
        "relation": {
            "relationType": "INCREMENTAL_TABLE",
            "selectQuery": "SELECT 4",
            "incrementalTableConfig": {
                "incrementalSelectQuery": "SELECT 4 WHERE ts > @cutoff",
                "incrementalPreOperations": ["SET @cutoff = ..."],
            },
        },
    }
    out = ddl.reconstruct(action)
    assert out.startswith("CREATE OR REPLACE TABLE `proj.ds.orders` AS\nSELECT 4;")
    assert "-- INCREMENTAL LOGIC (not executed; full-refresh emitted above)" in out
    assert "-- SELECT 4 WHERE ts > @cutoff" in out
    assert "-- SET @cutoff = ..." in out

def test_operations_joined():
    action = {"target": TARGET, "operations": {"queries": ["CALL foo()", "CALL bar();"]}}
    assert ddl.reconstruct(action) == "CALL foo();\n\nCALL bar();"

def test_operations_skipped_when_disabled():
    action = {"target": TARGET, "operations": {"queries": ["CALL foo()"]}}
    assert ddl.reconstruct(action, include_operations=False) is None

def test_assertion_off_by_default():
    action = {"target": TARGET, "assertion": {"selectQuery": "SELECT * FROM x WHERE bad"}}
    assert ddl.reconstruct(action) is None

def test_assertion_emitted_when_enabled():
    action = {"target": TARGET, "assertion": {"selectQuery": "SELECT * FROM x WHERE bad"}}
    out = ddl.reconstruct(action, include_assertions=True)
    assert out == ("-- Assertion (expects zero rows): `proj.ds.orders`\n"
                   "SELECT * FROM x WHERE bad;")

def test_declaration_skipped():
    assert ddl.reconstruct({"target": TARGET, "declaration": {}}) is None

def test_relation_missing_select_query_raises():
    action = {"target": TARGET, "relation": {"relationType": "TABLE"}}
    with pytest.raises(ValueError):
        ddl.reconstruct(action)

def test_unknown_action_raises():
    with pytest.raises(ValueError):
        ddl.reconstruct({"target": TARGET})
