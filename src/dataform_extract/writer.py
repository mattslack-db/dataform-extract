"""Map compiled-action filePaths to safe local output paths and write them."""
from pathlib import Path, PurePosixPath


class UnsafePathError(Exception):
    """Raised when a filePath would escape the output root."""


def output_path(out_root: Path, file_path: str) -> Path:
    rel = PurePosixPath(file_path)
    if rel.is_absolute() or any(part == ".." for part in rel.parts):
        raise UnsafePathError(f"refusing unsafe path: {file_path!r}")
    parts = list(rel.parts)
    if not parts:
        raise UnsafePathError(f"refusing unsafe path: {file_path!r}")
    name = parts[-1]
    if name.endswith(".sqlx"):
        parts[-1] = name[:-5] + ".sql"
    return out_root.joinpath(*parts)


def write_sql(out_root: Path, file_path: str, sql: str) -> Path:
    target = output_path(out_root, file_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(sql + "\n", encoding="utf-8")
    return target
