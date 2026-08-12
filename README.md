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
