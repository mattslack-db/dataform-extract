# dataform-extract

Compile a Google Cloud **Dataform** repository via the REST API and write a
local, folder-mirrored tree of runnable `.sql` files — ready for a Lakebridge
SQL conversion flow.

## Requirements

- Python 3.11+
- Google Cloud SDK (`gcloud`), authenticated: `gcloud auth login`
- The caller needs the `dataform.compilationResults.create` and
  `dataform.compilationResults.query` permissions.

No third-party Python packages are required (standard library only).

## Usage

```bash
PYTHONPATH=src python -m dataform_extract \
  --repo projects/PROJECT/locations/REGION/repositories/REPO \
  --commitish main \
  --out ./out
```

Options:

| Flag | Description |
|------|-------------|
| `--repo` | `projects/{PROJECT}/locations/{REGION}/repositories/{REPO}` (required) |
| `--commitish` | Git commitish to compile, e.g. `main` (mutually exclusive with `--workspace`) |
| `--workspace` | Workspace name to compile (mutually exclusive with `--commitish`) |
| `--out` | Output root directory (required) |
| `--path-filter` | Only export actions whose `filePath` starts with this prefix |
| `--include-assertions` | Emit assertion SELECTs (default: off) |
| `--no-include-operations` | Skip `operations` queries (default: included) |

Output mirrors each action's repo `filePath`, renaming `.sqlx` to `.sql`.

## What each file contains

- **Tables / materialized views:** `preOperations`, then
  `CREATE OR REPLACE TABLE ... AS <selectQuery>`, then `postOperations`.
- **Views:** `CREATE OR REPLACE VIEW ... AS <selectQuery>`.
- **Incremental tables:** the full-refresh `CREATE OR REPLACE TABLE` form, with
  the incremental logic preserved as a trailing SQL comment block.
- **Operations:** the raw `queries`, `;`-separated.
- **Assertions:** the SELECT (only with `--include-assertions`).
- **Declarations:** skipped (no SQL).

## Manual smoke test

Against a real repo you can access:

```bash
PYTHONPATH=src python -m dataform_extract \
  --repo projects/my-proj/locations/us-central1/repositories/my-repo \
  --commitish main --out ./out
ls -R ./out
```

## Development

```bash
pytest -v
```
