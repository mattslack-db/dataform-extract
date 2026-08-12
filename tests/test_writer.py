from pathlib import Path
import pytest
from dataform_extract.writer import output_path, write_sql, UnsafePathError

def test_maps_sqlx_to_sql_preserving_dirs():
    out = output_path(Path("/tmp/out"), "definitions/marts/orders.sqlx")
    assert out == Path("/tmp/out/definitions/marts/orders.sql")

def test_non_sqlx_extension_preserved():
    out = output_path(Path("/tmp/out"), "definitions/notes.sql")
    assert out == Path("/tmp/out/definitions/notes.sql")

def test_rejects_parent_traversal():
    with pytest.raises(UnsafePathError):
        output_path(Path("/tmp/out"), "../../etc/passwd")

def test_rejects_absolute_path():
    with pytest.raises(UnsafePathError):
        output_path(Path("/tmp/out"), "/etc/passwd")

def test_write_sql_creates_dirs_and_appends_newline(tmp_path):
    written = write_sql(tmp_path, "definitions/orders.sqlx", "SELECT 1;")
    assert written == tmp_path / "definitions/orders.sql"
    assert written.read_text() == "SELECT 1;\n"
