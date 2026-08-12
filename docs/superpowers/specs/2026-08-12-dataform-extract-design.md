# dataform-extract — Design

**Date:** 2026-08-12
**Status:** Approved

## Purpose

A single-purpose Python CLI that compiles a Google Cloud Dataform repository via
the Dataform REST API and writes a local, folder-mirrored tree of **runnable
`.sql` files**. The output is intended as input to a Lakebridge SQL conversion
flow, so each file contains reconstructed, executable BigQuery DDL rather than
raw SQLX.

## Why the API (not local parsing)

Local `.sqlx` files cannot be turned into runnable SQL by reading them alone:
SQLX carries `config {}` blocks, `${ref()}` / `${self()}` templating, JS blocks,
and `includes/` functions that only Dataform's compiler resolves. We therefore
compile the repository on GCP and consume the compiled actions, which already
have references resolved and targets assigned.

The source lives in an existing **GCP Dataform repository**. The user-facing
"input folder" is realized as an optional **path-prefix filter** over the
compiled actions' `filePath` values; the output tree mirrors those paths.

## Interface (CLI)

```
python -m dataform_extract \
  --repo projects/PROJECT/locations/REGION/repositories/REPO \
  --commitish main \                    # OR --workspace <name> (mutually exclusive)
  --out ./out \                         # output root directory
  --path-filter definitions/marts \     # optional; only export actions whose filePath starts here
  --include-assertions \                # optional (default: off)
  --include-operations                  # optional (default: on)
```

- **Auth:** shells out to `gcloud auth print-access-token`. Fails fast with a
  clear message if gcloud is missing or not authenticated.
- **Dependencies:** Python **standard library only** (`urllib.request`,
  `subprocess`, `argparse`, `json`, `pathlib`). No `requests` / `google-auth`.
- `--commitish` and `--workspace` are mutually exclusive; exactly one required.

## Module layout

```
src/dataform_extract/
├── __main__.py       # CLI entry: wires everything, exit codes
├── cli.py            # arg parsing + validation (mutually-exclusive commitish/workspace)
├── auth.py           # get_access_token() via gcloud subprocess
├── api.py            # DataformClient: create_compilation_result(), query_actions() (pagination)
├── ddl.py            # pure functions: action dict -> reconstructed SQL string (no I/O)
└── writer.py         # filePath -> mirrored output path; safe write under --out
```

`ddl.py` is pure (dict in, string out) for trivial unit testing with no network.

## Flow

1. `auth.get_access_token()` — one token, reused for both calls.
2. `POST .../compilationResults` with `{"gitCommitish": "main"}` **or**
   `{"workspace": ".../workspaces/<name>"}` → capture returned `name`.
3. `GET .../{name}:query`, following `nextPageToken` until exhausted → full list
   of `compilationResultActions`.
4. For each action: apply `--path-filter`, dispatch on type, reconstruct SQL via
   `ddl.py`, write to `<out>/<filePath with .sqlx→.sql>`.
5. Print summary: N written, N skipped (filtered / declarations), N warnings.

## API response schema (verified)

`compilationResultActions[]`, each a `CompilationResultAction`:

- `filePath` (string) — path incl. filename, relative to workspace root.
- `target` — `{ database, schema, name }`.
- Union field, one of:
  - `relation`: `relationType` (`TABLE` | `VIEW` | `INCREMENTAL_TABLE` |
    `MATERIALIZED_VIEW`), `selectQuery`, `preOperations[]`, `postOperations[]`,
    and `incrementalTableConfig` (`incrementalSelectQuery`,
    `incrementalPreOperations[]`, `incrementalPostOperations[]`).
  - `operations`: `queries[]`.
  - `assertion`: `selectQuery`.
  - `declaration`: external relation, documentation only (no SQL).
- Pagination: request `pageSize` / `pageToken`; response `nextPageToken`.

## DDL reconstruction rules

Target reference is `` `{database}.{schema}.{name}` `` (backtick-quoted).

- **relation → TABLE / MATERIALIZED_VIEW**: `preOperations` (each `;`-terminated)
  → `CREATE OR REPLACE TABLE <ref> AS\n<selectQuery>;` → `postOperations`.
- **relation → VIEW**: same, but `CREATE OR REPLACE VIEW <ref> AS ...`.
- **relation → INCREMENTAL_TABLE**: emit the **full-refresh** form —
  `CREATE OR REPLACE TABLE <ref> AS <selectQuery>` (+ pre/post ops). The
  incremental variant from `incrementalTableConfig` is appended **as a trailing
  SQL comment block** so nothing is lost but the file stays runnable. Flagged in
  the summary.
- **operations**: join `queries[]` with `;\n\n`. Controlled by
  `--include-operations` (default on).
- **assertion**: emit `selectQuery` as-is (a SELECT expected to return 0 rows),
  with a header comment. Only when `--include-assertions`.
- **declaration**: **skipped** (no SQL). Counted in summary.

## Error handling

- gcloud not found / not authed → clear message, exit 2.
- HTTP non-2xx → surface status + response body, exit 1 (never silently swallow).
- Unknown/empty action type or missing `selectQuery` → warn, skip that action,
  continue (partial success is useful).
- `filePath` sanitized against `..` / absolute-path traversal before writing.
- Never write outside `--out`; create parent dirs as needed.

## Test plan

- **Unit (bulk of coverage):** `ddl.py` against recorded action fixtures — one
  per type (table, view, incremental, operations, assertion, declaration),
  asserting exact reconstructed SQL. `writer.py` path mapping incl. traversal
  rejection. `cli.py` arg validation.
- **Integration:** `api.py` pagination against a stubbed HTTP layer (fake
  `urlopen`) — no live GCP.
- **No live-API test** in the suite (needs real creds); provide a documented
  manual smoke-test command in the README.

## Out of scope (YAGNI)

- Pushing local files into a workspace before compiling.
- Reconstructing exact incremental MERGE/INSERT execution logic.
- Non-BigQuery Dataform targets.
- Release configs / scheduling.
