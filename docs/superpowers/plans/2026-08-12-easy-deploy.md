# Easy Deploy (no pip/pipx) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `dataform-extract` deploy and run on a Mac with no pip/pipx — via a clone-and-run launcher and a single-file zipapp — plus a `--version` flag and thorough docs/examples.

**Architecture:** No packaging backend. Two run vehicles wrap the existing stdlib-only package: a bash launcher that sets `PYTHONPATH` and runs `python3 -m dataform_extract`, and a `python -m zipapp` single-file executable. A `--version` flag reads an in-package `__version__`. README documents three run methods, examples, and troubleshooting. A GitHub Release hosts the single file.

**Tech Stack:** Python 3.11+ standard library, `python -m zipapp`, bash, pytest, `gh` CLI (release only).

## Global Constraints

- **No pip / pipx / build-backend / console-script** packaging. Do NOT add `[build-system]` or `[project.scripts]` to `pyproject.toml`.
- **Standard library only** for runtime; bash + `python3` are the only things a user needs on PATH.
- **Python 3.11+**.
- **Version string is exactly `0.1.0`** and must match between `src/dataform_extract/__init__.py` and every test/asset that references it.
- **zipapp exit codes must be preserved**: the zipapp entry point must `raise SystemExit(main())` (not call `main()` bare), or the process always exits 0.
- Keep the `src/` layout; tests resolve it via the existing `pyproject.toml` `pythonpath = ["src"]`.

---

### Task 1: `--version` flag + `__version__`

**Files:**
- Modify: `src/dataform_extract/__init__.py`
- Modify: `src/dataform_extract/cli.py`
- Test: `tests/test_cli.py`

**Interfaces:**
- Consumes: existing `parse_args(argv) -> Args`.
- Produces: `dataform_extract.__version__: str` (value `"0.1.0"`); a `--version` argparse action that prints `dataform-extract 0.1.0` to stdout and exits 0. `--version` short-circuits argparse before required-arg validation (so it works with no other args).

- [ ] **Step 1: Write the failing test**

```python
# add to tests/test_cli.py
def test_version_flag_prints_and_exits_zero(capsys):
    with pytest.raises(SystemExit) as exc:
        parse_args(["--version"])
    assert exc.value.code == 0
    out = capsys.readouterr().out
    assert out.strip() == "dataform-extract 0.1.0"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONPATH=src python -m pytest tests/test_cli.py::test_version_flag_prints_and_exits_zero -v`
Expected: FAIL (argparse errors on missing `--repo`/source instead of printing version → `SystemExit` code 2, or no version output).

- [ ] **Step 3: Add `__version__`**

Set the contents of `src/dataform_extract/__init__.py` to:

```python
"""Compile a GCP Dataform repository and emit a mirrored tree of .sql files."""

__version__ = "0.1.0"
```

- [ ] **Step 4: Add the `--version` action in `cli.py`**

At the top of `src/dataform_extract/cli.py`, add the import (after the existing imports):

```python
from dataform_extract import __version__
```

Inside `parse_args`, immediately after `parser = argparse.ArgumentParser(...)` is constructed, add:

```python
    parser.add_argument("--version", action="version",
                        version=f"dataform-extract {__version__}")
```

- [ ] **Step 5: Run test to verify it passes**

Run: `PYTHONPATH=src python -m pytest tests/test_cli.py -v`
Expected: PASS (all cli tests, including the new one).

- [ ] **Step 6: Commit**

```bash
git add src/dataform_extract/__init__.py src/dataform_extract/cli.py tests/test_cli.py
git commit -m "feat: add --version flag and package __version__"
```

---

### Task 2: Clone-and-run launcher script

**Files:**
- Create: `dataform-extract` (repo root, executable)
- Test: `tests/test_launcher.py`

**Interfaces:**
- Consumes: `python3 -m dataform_extract` (the module entry) and the `--version` flag from Task 1.
- Produces: an executable `./dataform-extract` that forwards all args to the module with `PYTHONPATH` pointing at the repo's `src`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_launcher.py
import subprocess
import sys
from pathlib import Path

LAUNCHER = Path(__file__).resolve().parents[1] / "dataform-extract"

def test_launcher_version():
    result = subprocess.run([str(LAUNCHER), "--version"],
                            capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "dataform-extract 0.1.0"

def test_launcher_help_mentions_repo_flag():
    result = subprocess.run([str(LAUNCHER), "--help"],
                            capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert "--repo" in result.stdout
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONPATH=src python -m pytest tests/test_launcher.py -v`
Expected: FAIL (launcher file does not exist → `FileNotFoundError` / non-zero).

- [ ] **Step 3: Create the launcher**

Create `dataform-extract` at the repo root with exactly:

```bash
#!/usr/bin/env bash
# Run dataform-extract straight from a clone — no pip/pipx/venv needed.
set -euo pipefail
here="$(cd "$(dirname "$0")" && pwd)"
export PYTHONPATH="$here/src"
exec python3 -m dataform_extract "$@"
```

Then make it executable so the bit is committed:

```bash
chmod +x dataform-extract
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `PYTHONPATH=src python -m pytest tests/test_launcher.py -v`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add dataform-extract tests/test_launcher.py
git commit -m "feat: add clone-and-run launcher script"
```

---

### Task 3: Single-file zipapp build + preserved exit codes

**Files:**
- Modify: `src/dataform_extract/__main__.py`
- Create: `scripts/build-zipapp.sh` (executable)
- Modify: `.gitignore`
- Test: `tests/test_zipapp.py`

**Interfaces:**
- Consumes: the package `dataform_extract` and `main()`.
- Produces: `dataform_extract.__main__._entry()` (raises `SystemExit(main())`); `scripts/build-zipapp.sh` writing `dist/dataform-extract` (self-contained, shebang'd, executable). Build is idempotent and self-checks the artifact.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_zipapp.py
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BUILD = ROOT / "scripts" / "build-zipapp.sh"
ARTIFACT = ROOT / "dist" / "dataform-extract"

def test_build_zipapp_produces_runnable_artifact():
    build = subprocess.run([str(BUILD)], capture_output=True, text=True)
    assert build.returncode == 0, build.stdout + build.stderr
    assert ARTIFACT.exists()
    ver = subprocess.run([str(ARTIFACT), "--version"], capture_output=True, text=True)
    assert ver.returncode == 0, ver.stderr
    assert ver.stdout.strip() == "dataform-extract 0.1.0"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONPATH=src python -m pytest tests/test_zipapp.py -v`
Expected: FAIL (build script does not exist).

- [ ] **Step 3: Add the zipapp entry point in `__main__.py`**

At the bottom of `src/dataform_extract/__main__.py`, replace the existing:

```python
if __name__ == "__main__":
    raise SystemExit(main())
```

with:

```python
def _entry() -> None:
    """Console/zipapp entry point: run main() and exit with its return code."""
    raise SystemExit(main())


if __name__ == "__main__":
    _entry()
```

(This gives the zipapp a callable that propagates the exit code — `python -m zipapp -m "...:_entry"` generates a launcher that calls `_entry()`, and its `SystemExit` sets the process exit code. Calling bare `main()` would discard the returned code and always exit 0.)

- [ ] **Step 4: Create the build script**

Create `scripts/build-zipapp.sh` with exactly:

```bash
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
```

Make it executable:

```bash
chmod +x scripts/build-zipapp.sh
```

- [ ] **Step 5: Ignore build outputs**

Append to `.gitignore`:

```
dist/
build/
```

- [ ] **Step 6: Run test to verify it passes**

Run: `PYTHONPATH=src python -m pytest tests/test_zipapp.py -v`
Expected: PASS (build succeeds, artifact runs `--version`).

- [ ] **Step 7: Run the full suite**

Run: `PYTHONPATH=src python -m pytest -q`
Expected: PASS (all tests across the project).

- [ ] **Step 8: Commit**

```bash
git add src/dataform_extract/__main__.py scripts/build-zipapp.sh .gitignore tests/test_zipapp.py
git commit -m "feat: single-file zipapp build with preserved exit codes"
```

---

### Task 4: README rewrite (install-free docs + examples)

**Files:**
- Modify: `README.md`

**Interfaces:**
- Consumes: the finished launcher, zipapp build, and `--version`.
- Produces: user-facing docs. No code / tests.

- [ ] **Step 1: Rewrite `README.md`**

Replace the file contents with the following (verbatim):

````markdown
# dataform-extract

Compile a Google Cloud **Dataform** repository via the REST API and write a
local, folder-mirrored tree of runnable `.sql` files — ready for a Lakebridge
SQL conversion flow. Pure Python standard library: **no pip, no pipx, no
dependencies.**

## Prerequisites

- **`python3` 3.11+** on your PATH (`python3 --version`). Install from
  <https://www.python.org/downloads/> or `brew install python`.
- **Google Cloud SDK** installed and authenticated:
  ```bash
  brew install --cask google-cloud-sdk
  gcloud auth login
  ```
- IAM on the target repo: `dataform.compilationResults.create` and
  `dataform.compilationResults.query`.

## Run it — three ways (no install)

### 1. Single file (easiest to deploy)

Download the one self-contained executable from the latest
[Release](https://github.com/mattslack-db/dataform-extract/releases), then run it:

```bash
curl -L -o dataform-extract \
  https://github.com/mattslack-db/dataform-extract/releases/latest/download/dataform-extract
chmod +x dataform-extract
./dataform-extract --help
```

Copy that single file anywhere on the laptop — it needs only `python3`.

### 2. Clone and run

```bash
git clone https://github.com/mattslack-db/dataform-extract
cd dataform-extract
./dataform-extract --help
```

### 3. Straight from the module (no files created)

```bash
git clone https://github.com/mattslack-db/dataform-extract
cd dataform-extract
PYTHONPATH=src python3 -m dataform_extract --help
```

All three accept the same flags below. Examples use `./dataform-extract`.

## Options

| Flag | Description |
|------|-------------|
| `--repo` | `projects/{PROJECT}/locations/{REGION}/repositories/{REPO}` (required) |
| `--commitish` | Git commitish to compile, e.g. `main` (mutually exclusive with `--workspace`) |
| `--workspace` | Workspace name to compile (mutually exclusive with `--commitish`) |
| `--out` | Output root directory (required) |
| `--path-filter` | Only export actions whose `filePath` starts with this prefix |
| `--include-assertions` | Emit assertion SELECTs (default: off) |
| `--no-include-operations` | Skip `operations` queries (default: included) |
| `--version` | Print the version and exit |

## Examples

Compile the `main` branch of a repo and write the full `.sql` tree:

```bash
./dataform-extract \
  --repo projects/my-proj/locations/us-central1/repositories/my-repo \
  --commitish main \
  --out ./out
```

Compile a development **workspace** instead of a branch:

```bash
./dataform-extract \
  --repo projects/my-proj/locations/us-central1/repositories/my-repo \
  --workspace my-workspace \
  --out ./out
```

Export **only a subfolder** (references outside it are still fully resolved,
because the whole project compiles first):

```bash
./dataform-extract \
  --repo projects/my-proj/locations/us-central1/repositories/my-repo \
  --commitish main \
  --path-filter definitions/marts \
  --out ./out
```

Include assertions, and skip `operations` blocks:

```bash
./dataform-extract \
  --repo projects/my-proj/locations/us-central1/repositories/my-repo \
  --commitish main \
  --include-assertions --no-include-operations \
  --out ./out
```

## Sample output

```
$ ./dataform-extract --repo projects/p/locations/us-central1/repositories/r --commitish main --out ./out
Wrote 3 .sql file(s) to ./out (0 skipped, 0 warning(s), 1 incremental).

$ cat ./out/definitions/marts/orders_view.sql
CREATE OR REPLACE VIEW `p.dataform.orders_view` AS
SELECT id FROM `p.dataform.orders`;
```

Output mirrors each action's repo `filePath`, renaming `.sqlx` to `.sql`.
`${ref()}` and config are resolved by Dataform's compiler.

### What each file contains

- **Tables / materialized views:** `preOperations`, then
  `CREATE OR REPLACE TABLE ... AS <selectQuery>`, then `postOperations`.
- **Views:** `CREATE OR REPLACE VIEW ... AS <selectQuery>`.
- **Incremental tables:** the full-refresh `CREATE OR REPLACE TABLE` form, with
  the incremental logic preserved as a trailing SQL comment block.
- **Operations:** the raw `queries`, `;`-separated.
- **Assertions:** the SELECT (only with `--include-assertions`).
- **Declarations:** skipped (no SQL).

## Build the single file yourself

```bash
./scripts/build-zipapp.sh      # writes dist/dataform-extract
./dist/dataform-extract --version
```

## Troubleshooting

| Symptom | Cause / fix |
|---------|-------------|
| Exit code 2, "gcloud not found" / "Failed to get access token" | Install the Google Cloud SDK and run `gcloud auth login`. |
| Exit code 1, `HTTP 403 ... permission denied` | Your account lacks Dataform IAM on the repo (`dataform.compilationResults.create`/`.query`). |
| Exit code 1, `network error contacting ...` | No connectivity / DNS failure reaching `dataform.googleapis.com`. |
| Exit code 1, `HTTP 404 ... not found` | Wrong `--repo`, `--commitish`, or `--workspace`. |
| `WARN: 0 SQL files written` | Repo empty, fully filtered out, or failed to compile (compilation errors are not surfaced). |
| `python3: command not found` | Install Python 3.11+ (python.org or `brew install python`). |

## Exit codes

- `0` — success
- `1` — API error (HTTP failure, network error)
- `2` — auth error (gcloud missing or not authenticated)

## Development

```bash
PYTHONPATH=src python3 -m pytest -q
```
````

- [ ] **Step 2: Commit**

```bash
git add README.md
git commit -m "docs: install-free README with three run methods, examples, troubleshooting"
```

---

## Finishing Step (controller-run, not a subagent): GitHub Release

After Tasks 1–4 are merged to `main`, the controller performs this once (it is
outward-facing and uses the `mattslack-db` gh account):

- [ ] Build from the merged `main`: `./scripts/build-zipapp.sh`
- [ ] Create the release and upload the single-file asset:

```bash
gh release create v0.1.0 dist/dataform-extract \
  --repo mattslack-db/dataform-extract \
  --title "v0.1.0" \
  --notes "Single-file, dependency-free dataform-extract. Download the dataform-extract asset, chmod +x, run."
```

- [ ] Verify the documented download URL resolves:
  `https://github.com/mattslack-db/dataform-extract/releases/latest/download/dataform-extract`

---

## Self-Review

**Spec coverage:**
- Clone-and-run launcher → Task 2. ✅
- Single-file zipapp + build script + self-check + `dist/`,`build/` gitignore → Task 3. ✅
- Preserved zipapp exit codes (`_entry`) → Task 3 (Global Constraints). ✅
- `--version` + `__version__` → Task 1. ✅
- README: prerequisites, three run methods, examples, sample output, build-it-yourself, troubleshooting, exit codes → Task 4. ✅
- GitHub Release v0.1.0 with asset → Finishing Step. ✅
- No pip/pipx/build-backend added → Global Constraints; no task touches `[build-system]`. ✅

**Placeholder scan:** No TBD/TODO; every code, script, test, and doc step is concrete. ✅

**Type/name consistency:** `__version__` = `"0.1.0"` used identically in Task 1 code and Tasks 1–3 tests; `_entry` defined in Task 3 and referenced by the Task 3 build script's `-m "dataform_extract.__main__:_entry"`; launcher/build artifact paths (`dataform-extract`, `dist/dataform-extract`) consistent across tasks and README. ✅
