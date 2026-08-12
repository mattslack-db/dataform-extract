import pytest
from dataform_extract.cli import parse_args, Args

BASE = ["--repo", "projects/p/locations/us/repositories/r", "--out", "./out"]

def test_parses_commitish_and_defaults():
    args = parse_args(BASE + ["--commitish", "main"])
    assert args == Args(
        repo="projects/p/locations/us/repositories/r",
        commitish="main", workspace=None, out="./out",
        path_filter=None, include_assertions=False, include_operations=True,
    )

def test_parses_workspace_and_flags():
    args = parse_args(BASE + ["--workspace", "ws", "--path-filter", "definitions/marts",
                              "--include-assertions", "--no-include-operations"])
    assert args.workspace == "ws"
    assert args.commitish is None
    assert args.path_filter == "definitions/marts"
    assert args.include_assertions is True
    assert args.include_operations is False

def test_commitish_and_workspace_mutually_exclusive():
    with pytest.raises(SystemExit):
        parse_args(BASE + ["--commitish", "main", "--workspace", "ws"])

def test_requires_one_of_commitish_or_workspace():
    with pytest.raises(SystemExit):
        parse_args(BASE)
