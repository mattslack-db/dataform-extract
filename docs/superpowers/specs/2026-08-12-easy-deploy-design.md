# Easy Deploy (no pip/pipx) — Design

**Date:** 2026-08-12
**Status:** Approved

## Purpose

Make `dataform-extract` as easy as possible to deploy and run on a Mac laptop
**without pip or pipx**. Because the tool is standard-library-only (zero
third-party runtime deps), it can ship as a single self-contained file and also
run straight from a clone. Add documentation and worked examples so a new user
is productive immediately.

## Non-goals

- No pip / pipx / build-backend / console-script packaging (explicitly excluded).
- No Homebrew formula/tap.
- No changes to the tool's behavior beyond adding a `--version` flag.

## Deliverables

### 1. Clone-and-run launcher

`dataform-extract` at the repo root, executable:

```sh
#!/usr/bin/env bash
here="$(cd "$(dirname "$0")" && pwd)"
export PYTHONPATH="$here/src"
exec python3 -m dataform_extract "$@"
```

Usage after `git clone`: `./dataform-extract --repo … --commitish main --out ./out`.
No build, no install, no manual `PYTHONPATH`.

### 2. Single-file zipapp build

`scripts/build-zipapp.sh` produces `dist/dataform-extract` — a self-contained,
shebang'd (`/usr/bin/env python3`) executable built with `python -m zipapp` from
a pycache-free staging copy of `src/dataform_extract`.

Behavior:
- Stage: copy `src/dataform_extract` into a temp/`build/` dir, strip `__pycache__`.
- Build: `python3 -m zipapp <stage> -m "dataform_extract.__main__:main" -p "/usr/bin/env python3" -o dist/dataform-extract`.
- `chmod +x dist/dataform-extract`.
- Self-check: run `dist/dataform-extract --version` and `dist/dataform-extract --help`; fail the script (non-zero exit) if either fails.
- Idempotent: safe to re-run; cleans `build/` staging each time.

Deploy: copy `dist/dataform-extract` anywhere, `chmod +x`, run. Only requires a
`python3` on PATH.

`dist/` and `build/` are git-ignored (add to `.gitignore`).

### 3. GitHub Release

Cut `v0.1.0` on `mattslack-db/dataform-extract` and upload `dist/dataform-extract`
as a release asset, enabling the zero-clone path:

```sh
curl -L -o dataform-extract <release-asset-url>
chmod +x dataform-extract
./dataform-extract --help
```

(Release creation is a one-time ops step performed after the build artifact is
produced; documented in the README.)

### 4. `--version` flag

- Add `__version__ = "0.1.0"` to `src/dataform_extract/__init__.py`.
- In `cli.py`, add an argparse `--version` action that prints
  `dataform-extract {__version__}` and exits 0.
- Works across all three run methods (module, launcher, zipapp) because it reads
  the in-package constant, not pip metadata.
- One unit test asserts `--version` exits 0 and prints the version string.

### 5. Documentation (README rewrite)

Sections:
- **What it does** (one paragraph, unchanged intent).
- **Prerequisites**: a `python3` (3.11+) on PATH; Google Cloud SDK installed
  (`brew install --cask google-cloud-sdk`) and authenticated (`gcloud auth login`);
  required IAM: `dataform.compilationResults.create` + `.query` on the repo.
- **Three ways to run**, easiest first:
  1. Download the single file from the latest Release (curl + chmod).
  2. Clone + `./dataform-extract …` (launcher).
  3. `PYTHONPATH=src python -m dataform_extract …` (no files at all).
- **Examples** (worked, copy-pasteable): compile a branch (`--commitish main`);
  compile a workspace (`--workspace ws`); export only a subfolder
  (`--path-filter definitions/marts`); include assertions
  (`--include-assertions`); skip operations (`--no-include-operations`).
- **Sample output**: the summary line + an example generated `.sql` file
  (table with resolved `${ref()}`), and the mirrored-tree note.
- **Building the single file yourself**: `scripts/build-zipapp.sh` → `dist/dataform-extract`.
- **Troubleshooting**: exit codes (0 success / 1 API error / 2 auth error);
  `gcloud` not found or not authed (exit 2, run `gcloud auth login`); HTTP 403
  (missing Dataform IAM); network error (surfaces as a clean API error, exit 1);
  no `python3` on PATH (install via python.org or `brew install python`).

## Testing

- Unit: `--version` prints the version and exits 0 (argparse `SystemExit(0)`).
- The build script's own self-check (`--version`/`--help` on the built zipapp) is
  the acceptance test for the zipapp; run it manually during implementation and
  document the command. Not a pytest case (it shells out and builds an artifact).
- Full existing suite stays green.

## Out of scope (YAGNI)

- Auto-installing python3 or gcloud.
- CI to auto-publish releases (manual `gh release create` for now).
- Windows/Linux launcher variants (Mac-focused; the zipapp is portable anyway).
