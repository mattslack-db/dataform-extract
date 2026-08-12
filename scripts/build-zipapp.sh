#!/usr/bin/env bash
# Build a single-file, self-contained executable (Python zipapp) at
# dist/dataform-extract. No pip/pipx — works because the tool is stdlib-only.
set -euo pipefail

here="$(cd "$(dirname "$0")/.." && pwd)"   # repo root (this script lives in scripts/)
stage="$here/build/stage"
out="$here/dist/dataform-extract"

rm -rf "$here/build" "$out"
mkdir -p "$stage" "$here/dist"

# Stage a pycache-free copy of the package.
cp -R "$here/src/dataform_extract" "$stage/"
find "$stage" -name '__pycache__' -type d -prune -exec rm -rf {} +

# Pack into a single shebang'd, executable file.
python3 -m zipapp "$stage" \
  -m "dataform_extract.__main__:_entry" \
  -p "/usr/bin/env python3" \
  -o "$out"
chmod +x "$out"

# Self-check: the artifact must run.
echo "built $out"
"$out" --version
"$out" --help >/dev/null
echo "self-check passed"
rm -rf "$here/build"
