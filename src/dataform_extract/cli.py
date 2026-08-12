"""Command-line argument parsing and validation."""
import argparse
from dataclasses import dataclass


@dataclass(frozen=True)
class Args:
    repo: str
    commitish: str | None
    workspace: str | None
    out: str
    path_filter: str | None
    include_assertions: bool
    include_operations: bool


def parse_args(argv: list[str]) -> Args:
    parser = argparse.ArgumentParser(
        prog="dataform-extract",
        description="Compile a GCP Dataform repo and write a mirrored tree of .sql files.",
    )
    parser.add_argument("--repo", required=True,
                        help="projects/{PROJECT}/locations/{REGION}/repositories/{REPO}")
    parser.add_argument("--out", required=True, help="Output root directory.")
    parser.add_argument("--path-filter", default=None,
                        help="Only export actions whose filePath starts with this prefix.")

    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--commitish", default=None, help="Git commitish to compile (e.g. main).")
    source.add_argument("--workspace", default=None, help="Workspace name to compile.")

    parser.add_argument("--include-assertions", action="store_true",
                        help="Emit assertion SELECT statements (default: off).")
    parser.add_argument("--include-operations", action=argparse.BooleanOptionalAction,
                        default=True, help="Emit operations queries (default: on).")

    ns = parser.parse_args(argv)
    return Args(
        repo=ns.repo, commitish=ns.commitish, workspace=ns.workspace, out=ns.out,
        path_filter=ns.path_filter, include_assertions=ns.include_assertions,
        include_operations=ns.include_operations,
    )
