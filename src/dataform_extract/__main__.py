"""CLI orchestration: compile a Dataform repo and write a mirrored .sql tree."""
import sys
from dataclasses import dataclass
from pathlib import Path

from .cli import Args, parse_args
from .auth import get_access_token, AuthError
from .api import DataformClient, ApiError
from . import ddl
from .writer import write_sql, UnsafePathError


@dataclass(frozen=True)
class Summary:
    written: int
    skipped: int
    warnings: int
    incremental: int


def _is_incremental(action: dict) -> bool:
    return action.get("relation", {}).get("relationType") == "INCREMENTAL_TABLE"


def run(args: Args, *, token_getter=get_access_token,
        client_factory=DataformClient) -> Summary:
    token = token_getter()
    client = client_factory(token)
    name = client.create_compilation_result(
        args.repo, commitish=args.commitish, workspace=args.workspace)
    actions = client.query_actions(name)

    out_root = Path(args.out)
    written = skipped = warnings = incremental = 0

    for action in actions:
        file_path = action.get("filePath", "")
        if args.path_filter and not file_path.startswith(args.path_filter):
            continue
        try:
            sql = ddl.reconstruct(
                action, include_operations=args.include_operations,
                include_assertions=args.include_assertions)
        except (ValueError, KeyError) as exc:
            print(f"WARN: skipping {file_path or '<no path>'}: {exc}", file=sys.stderr)
            warnings += 1
            continue
        if sql is None:
            skipped += 1
            continue
        try:
            write_sql(out_root, file_path, sql)
        except UnsafePathError as exc:
            print(f"WARN: {exc}", file=sys.stderr)
            warnings += 1
            continue
        written += 1
        if _is_incremental(action):
            incremental += 1

    return Summary(written, skipped, warnings, incremental)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    try:
        summary = run(args)
    except AuthError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    except ApiError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(f"Wrote {summary.written} .sql file(s) to {args.out} "
          f"({summary.skipped} skipped, {summary.warnings} warning(s), "
          f"{summary.incremental} incremental).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
