# dataform-extract Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A stdlib-only Python CLI that compiles a GCP Dataform repository via the REST API and writes a folder-mirrored tree of runnable `.sql` files for Lakebridge.

**Architecture:** Six small modules under `src/dataform_extract/`. `auth` gets a token via gcloud; `api` creates a compilation result and queries its actions (paginated); `ddl` is a pure dict→SQL reconstructor; `writer` maps `filePath`→safe output path; `cli` parses/validates args; `__main__` orchestrates and prints a summary.

**Tech Stack:** Python 3.11+ standard library only (`urllib.request`, `subprocess`, `argparse`, `json`, `pathlib`, `dataclasses`). pytest for tests. No third-party runtime dependencies.

## Global Constraints

- **Runtime dependencies:** Python standard library ONLY. No `requests`, no `google-auth`, no third-party runtime imports.
- **Immutability:** parsed args and results are frozen dataclasses / new objects; never mutate inputs.
- **Auth:** obtained solely via `gcloud auth print-access-token` (subprocess). No credential files parsed.
- **API base URL:** `https://dataform.googleapis.com/v1beta1`.
- **Repo identifier format:** `projects/{PROJECT}/locations/{REGION}/repositories/{REPO}` (passed verbatim as `--repo`).
- **`--commitish` and `--workspace` are mutually exclusive; exactly one is required.**
- **Test isolation:** no test may hit the network or call gcloud; `api` uses an injected opener, `auth` an injected runner.
- **Package import:** `src` layout; tests resolve it via `pyproject.toml` `[tool.pytest.ini_options] pythonpath = ["src"]`.

---

### Task 1: Project scaffold + CLI argument parsing

**Files:**
- Create: `pyproject.toml`
- Create: `src/dataform_extract/__init__.py` (empty)
- Create: `src/dataform_extract/cli.py`
- Test: `tests/test_cli.py`

**Interfaces:**
- Consumes: nothing.
- Produces:
  - `@dataclass(frozen=True) class Args` with fields: `repo: str`, `commitish: str | None`, `workspace: str | None`, `out: str`, `path_filter: str | None`, `include_assertions: bool`, `include_operations: bool`.
  - `parse_args(argv: list[str]) -> Args` — raises `SystemExit` (via argparse) on invalid/missing/mutually-exclusive args.

- [ ] **Step 1: Write `pyproject.toml`**

```toml
[project]
name = "dataform-extract"
version = "0.1.0"
requires-python = ">=3.11"

[tool.pytest.ini_options]
pythonpath = ["src"]
testpaths = ["tests"]
```

- [ ] **Step 2: Create empty package marker**

Create `src/dataform_extract/__init__.py` with a single line:

```python
"""Compile a GCP Dataform repository and emit a mirrored tree of .sql files."""
```

- [ ] **Step 3: Write the failing tests**

```python
# tests/test_cli.py
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
```

- [ ] **Step 4: Run tests to verify they fail**

Run: `pytest tests/test_cli.py -v`
Expected: FAIL (`ModuleNotFoundError: dataform_extract.cli`).

- [ ] **Step 5: Implement `cli.py`**

```python
# src/dataform_extract/cli.py
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
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `pytest tests/test_cli.py -v`
Expected: PASS (4 tests).

- [ ] **Step 7: Commit**

```bash
git add pyproject.toml src/dataform_extract/__init__.py src/dataform_extract/cli.py tests/test_cli.py
git commit -m "feat: project scaffold and CLI arg parsing"
```

---

### Task 2: Auth (gcloud access token)

**Files:**
- Create: `src/dataform_extract/auth.py`
- Test: `tests/test_auth.py`

**Interfaces:**
- Consumes: nothing.
- Produces:
  - `class AuthError(Exception)`.
  - `get_access_token(runner=subprocess.run) -> str` — runs `gcloud auth print-access-token`; returns the stripped token; raises `AuthError` if gcloud is missing (`FileNotFoundError`) or exits non-zero. `runner` is injectable for tests and must accept `(cmd_list, capture_output=True, text=True)` and return an object with `.returncode` and `.stdout`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_auth.py
import subprocess
import pytest
from dataform_extract.auth import get_access_token, AuthError


class FakeCompleted:
    def __init__(self, returncode, stdout="", stderr=""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def test_returns_stripped_token():
    def runner(cmd, capture_output, text):
        assert cmd == ["gcloud", "auth", "print-access-token"]
        return FakeCompleted(0, stdout="ya29.token-value\n")
    assert get_access_token(runner=runner) == "ya29.token-value"


def test_raises_when_gcloud_missing():
    def runner(cmd, capture_output, text):
        raise FileNotFoundError("gcloud")
    with pytest.raises(AuthError):
        get_access_token(runner=runner)


def test_raises_on_nonzero_exit():
    def runner(cmd, capture_output, text):
        return FakeCompleted(1, stdout="", stderr="not logged in")
    with pytest.raises(AuthError):
        get_access_token(runner=runner)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_auth.py -v`
Expected: FAIL (`ModuleNotFoundError`).

- [ ] **Step 3: Implement `auth.py`**

```python
# src/dataform_extract/auth.py
"""Obtain a GCP access token via the gcloud CLI."""
import subprocess


class AuthError(Exception):
    """Raised when a gcloud access token cannot be obtained."""


def get_access_token(runner=subprocess.run) -> str:
    cmd = ["gcloud", "auth", "print-access-token"]
    try:
        result = runner(cmd, capture_output=True, text=True)
    except FileNotFoundError as exc:
        raise AuthError(
            "gcloud not found on PATH. Install the Google Cloud SDK and run "
            "`gcloud auth login`."
        ) from exc
    if result.returncode != 0:
        raise AuthError(
            "Failed to get access token via gcloud. Run `gcloud auth login`.\n"
            f"{(result.stderr or '').strip()}"
        )
    return result.stdout.strip()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_auth.py -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add src/dataform_extract/auth.py tests/test_auth.py
git commit -m "feat: gcloud access-token auth"
```

---

### Task 3: DDL reconstruction (pure core)

**Files:**
- Create: `src/dataform_extract/ddl.py`
- Test: `tests/test_ddl.py`

**Interfaces:**
- Consumes: nothing.
- Produces:
  - `reconstruct(action: dict, *, include_operations: bool = True, include_assertions: bool = False) -> str | None` — returns reconstructed SQL, or `None` when the action is intentionally skipped (declaration, or a flag-disabled assertion/operations). Raises `ValueError` for malformed relations (missing `selectQuery`) or unrecognized action shapes.
  - Output rules: statements are joined with `\n\n`; each SQL statement is stripped and terminated with exactly one `;`; target ref is `` `{database}.{schema}.{name}` ``. No trailing newline (the writer adds one).

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_ddl.py
import pytest
from dataform_extract import ddl

TARGET = {"database": "proj", "schema": "ds", "name": "orders"}

def test_table_with_pre_and_post_ops():
    action = {
        "filePath": "definitions/orders.sqlx",
        "target": TARGET,
        "relation": {
            "relationType": "TABLE",
            "selectQuery": "SELECT 1 AS x",
            "preOperations": ["DELETE FROM `proj.ds.tmp` WHERE 1=1"],
            "postOperations": ["GRANT SELECT ON `proj.ds.orders` TO 'x'"],
        },
    }
    assert ddl.reconstruct(action) == (
        "DELETE FROM `proj.ds.tmp` WHERE 1=1;\n\n"
        "CREATE OR REPLACE TABLE `proj.ds.orders` AS\n"
        "SELECT 1 AS x;\n\n"
        "GRANT SELECT ON `proj.ds.orders` TO 'x';"
    )

def test_view():
    action = {"target": TARGET, "relation": {"relationType": "VIEW", "selectQuery": "SELECT 2"}}
    assert ddl.reconstruct(action) == "CREATE OR REPLACE VIEW `proj.ds.orders` AS\nSELECT 2;"

def test_materialized_view_uses_create_table():
    action = {"target": TARGET,
              "relation": {"relationType": "MATERIALIZED_VIEW", "selectQuery": "SELECT 3"}}
    assert ddl.reconstruct(action) == "CREATE OR REPLACE TABLE `proj.ds.orders` AS\nSELECT 3;"

def test_incremental_emits_full_refresh_plus_comment():
    action = {
        "target": TARGET,
        "relation": {
            "relationType": "INCREMENTAL_TABLE",
            "selectQuery": "SELECT 4",
            "incrementalTableConfig": {
                "incrementalSelectQuery": "SELECT 4 WHERE ts > @cutoff",
                "incrementalPreOperations": ["SET @cutoff = ..."],
            },
        },
    }
    out = ddl.reconstruct(action)
    assert out.startswith("CREATE OR REPLACE TABLE `proj.ds.orders` AS\nSELECT 4;")
    assert "-- INCREMENTAL LOGIC (not executed; full-refresh emitted above)" in out
    assert "-- SELECT 4 WHERE ts > @cutoff" in out
    assert "-- SET @cutoff = ..." in out

def test_operations_joined():
    action = {"target": TARGET, "operations": {"queries": ["CALL foo()", "CALL bar();"]}}
    assert ddl.reconstruct(action) == "CALL foo();\n\nCALL bar();"

def test_operations_skipped_when_disabled():
    action = {"target": TARGET, "operations": {"queries": ["CALL foo()"]}}
    assert ddl.reconstruct(action, include_operations=False) is None

def test_assertion_off_by_default():
    action = {"target": TARGET, "assertion": {"selectQuery": "SELECT * FROM x WHERE bad"}}
    assert ddl.reconstruct(action) is None

def test_assertion_emitted_when_enabled():
    action = {"target": TARGET, "assertion": {"selectQuery": "SELECT * FROM x WHERE bad"}}
    out = ddl.reconstruct(action, include_assertions=True)
    assert out == ("-- Assertion (expects zero rows): `proj.ds.orders`\n"
                   "SELECT * FROM x WHERE bad;")

def test_declaration_skipped():
    assert ddl.reconstruct({"target": TARGET, "declaration": {}}) is None

def test_relation_missing_select_query_raises():
    action = {"target": TARGET, "relation": {"relationType": "TABLE"}}
    with pytest.raises(ValueError):
        ddl.reconstruct(action)

def test_unknown_action_raises():
    with pytest.raises(ValueError):
        ddl.reconstruct({"target": TARGET})
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_ddl.py -v`
Expected: FAIL (`ModuleNotFoundError`).

- [ ] **Step 3: Implement `ddl.py`**

```python
# src/dataform_extract/ddl.py
"""Pure reconstruction of runnable SQL from a CompilationResultAction dict."""

_INCREMENTAL_HEADER = "-- INCREMENTAL LOGIC (not executed; full-refresh emitted above)"


def _target_ref(target: dict) -> str:
    return f"`{target['database']}.{target['schema']}.{target['name']}`"


def _terminate(sql: str) -> str:
    """Strip surrounding whitespace and trailing semicolons, then add exactly one."""
    return sql.strip().rstrip(";").rstrip() + ";"


def _comment_lines(text: str) -> list[str]:
    return [f"-- {line}" if line else "--" for line in text.splitlines() or [""]]


def _incremental_comment(config: dict) -> str:
    lines = ["", _INCREMENTAL_HEADER]
    fields = [
        ("incremental pre-operations", config.get("incrementalPreOperations", [])),
        ("incremental select query", config.get("incrementalSelectQuery")),
        ("incremental post-operations", config.get("incrementalPostOperations", [])),
    ]
    for label, value in fields:
        if not value:
            continue
        lines.append(f"-- {label}:")
        if isinstance(value, list):
            for item in value:
                lines.extend(_comment_lines(item))
        else:
            lines.extend(_comment_lines(value))
    return "\n".join(lines)


def _reconstruct_relation(relation: dict, ref: str) -> str:
    rel_type = relation.get("relationType")
    select_query = relation.get("selectQuery")
    if not select_query:
        raise ValueError(f"relation for {ref} has no selectQuery")

    keyword = "VIEW" if rel_type == "VIEW" else "TABLE"
    statements = [_terminate(op) for op in relation.get("preOperations", [])]
    statements.append(_terminate(f"CREATE OR REPLACE {keyword} {ref} AS\n{select_query}"))
    statements.extend(_terminate(op) for op in relation.get("postOperations", []))

    sql = "\n\n".join(statements)
    if rel_type == "INCREMENTAL_TABLE" and relation.get("incrementalTableConfig"):
        sql += "\n" + _incremental_comment(relation["incrementalTableConfig"])
    return sql


def reconstruct(action: dict, *, include_operations: bool = True,
                include_assertions: bool = False) -> str | None:
    ref = _target_ref(action["target"])

    if "declaration" in action:
        return None
    if "relation" in action:
        return _reconstruct_relation(action["relation"], ref)
    if "operations" in action:
        if not include_operations:
            return None
        queries = action["operations"].get("queries", [])
        return "\n\n".join(_terminate(q) for q in queries)
    if "assertion" in action:
        if not include_assertions:
            return None
        select_query = action["assertion"].get("selectQuery", "")
        return f"-- Assertion (expects zero rows): {ref}\n{_terminate(select_query)}"

    raise ValueError(f"unrecognized action shape for {ref}: keys={sorted(action)}")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_ddl.py -v`
Expected: PASS (11 tests).

- [ ] **Step 5: Commit**

```bash
git add src/dataform_extract/ddl.py tests/test_ddl.py
git commit -m "feat: pure DDL reconstruction from compiled actions"
```

---

### Task 4: Output-path writer (traversal-safe)

**Files:**
- Create: `src/dataform_extract/writer.py`
- Test: `tests/test_writer.py`

**Interfaces:**
- Consumes: nothing.
- Produces:
  - `class UnsafePathError(Exception)`.
  - `output_path(out_root: Path, file_path: str) -> Path` — maps a repo `filePath` to a target path under `out_root`, renaming a trailing `.sqlx` to `.sql`. Raises `UnsafePathError` if `file_path` is absolute or contains a `..` component.
  - `write_sql(out_root: Path, file_path: str, sql: str) -> Path` — creates parent dirs and writes `sql + "\n"`; returns the path written.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_writer.py
from pathlib import Path
import pytest
from dataform_extract.writer import output_path, write_sql, UnsafePathError

def test_maps_sqlx_to_sql_preserving_dirs():
    out = output_path(Path("/tmp/out"), "definitions/marts/orders.sqlx")
    assert out == Path("/tmp/out/definitions/marts/orders.sql")

def test_non_sqlx_extension_preserved():
    out = output_path(Path("/tmp/out"), "definitions/notes.sql")
    assert out == Path("/tmp/out/definitions/notes.sql")

def test_rejects_parent_traversal():
    with pytest.raises(UnsafePathError):
        output_path(Path("/tmp/out"), "../../etc/passwd")

def test_rejects_absolute_path():
    with pytest.raises(UnsafePathError):
        output_path(Path("/tmp/out"), "/etc/passwd")

def test_write_sql_creates_dirs_and_appends_newline(tmp_path):
    written = write_sql(tmp_path, "definitions/orders.sqlx", "SELECT 1;")
    assert written == tmp_path / "definitions/orders.sql"
    assert written.read_text() == "SELECT 1;\n"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_writer.py -v`
Expected: FAIL (`ModuleNotFoundError`).

- [ ] **Step 3: Implement `writer.py`**

```python
# src/dataform_extract/writer.py
"""Map compiled-action filePaths to safe local output paths and write them."""
from pathlib import Path, PurePosixPath


class UnsafePathError(Exception):
    """Raised when a filePath would escape the output root."""


def output_path(out_root: Path, file_path: str) -> Path:
    rel = PurePosixPath(file_path)
    if rel.is_absolute() or any(part == ".." for part in rel.parts):
        raise UnsafePathError(f"refusing unsafe path: {file_path!r}")
    parts = list(rel.parts)
    name = parts[-1]
    if name.endswith(".sqlx"):
        parts[-1] = name[:-5] + ".sql"
    return out_root.joinpath(*parts)


def write_sql(out_root: Path, file_path: str, sql: str) -> Path:
    target = output_path(out_root, file_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(sql + "\n")
    return target
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_writer.py -v`
Expected: PASS (5 tests).

- [ ] **Step 5: Commit**

```bash
git add src/dataform_extract/writer.py tests/test_writer.py
git commit -m "feat: traversal-safe output-path writer"
```

---

### Task 5: Dataform API client (create + paginated query)

**Files:**
- Create: `src/dataform_extract/api.py`
- Test: `tests/test_api.py`

**Interfaces:**
- Consumes: nothing (token passed in).
- Produces:
  - `BASE_URL = "https://dataform.googleapis.com/v1beta1"`.
  - `class ApiError(Exception)`.
  - `class DataformClient` constructed as `DataformClient(token: str, opener=..., base_url=BASE_URL)`. `opener` is a callable `(method: str, url: str, headers: dict, body: bytes | None) -> tuple[int, bytes]`; default performs a real `urllib.request` call.
    - `create_compilation_result(repo: str, *, commitish: str | None = None, workspace: str | None = None) -> str` — POSTs `{"gitCommitish": commitish}` or `{"workspace": f"{repo}/workspaces/{workspace}"}`; returns the `name` field.
    - `query_actions(compilation_result_name: str) -> list[dict]` — GETs `{name}:query`, following `nextPageToken`, concatenating `compilationResultActions`.
  - Non-2xx responses raise `ApiError` with status and body text.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_api.py
import json
import pytest
from dataform_extract.api import DataformClient, ApiError, BASE_URL

REPO = "projects/p/locations/us/repositories/r"

class RecordingOpener:
    """Returns queued responses and records requests."""
    def __init__(self, responses):
        self._responses = list(responses)   # list of (status, dict)
        self.calls = []
    def __call__(self, method, url, headers, body):
        self.calls.append((method, url, headers, body))
        status, payload = self._responses.pop(0)
        return status, json.dumps(payload).encode()

def test_create_compilation_result_with_commitish():
    opener = RecordingOpener([(200, {"name": f"{REPO}/compilationResults/abc"})])
    client = DataformClient("tok", opener=opener)
    name = client.create_compilation_result(REPO, commitish="main")
    assert name == f"{REPO}/compilationResults/abc"
    method, url, headers, body = opener.calls[0]
    assert method == "POST"
    assert url == f"{BASE_URL}/{REPO}/compilationResults"
    assert headers["Authorization"] == "Bearer tok"
    assert json.loads(body) == {"gitCommitish": "main"}

def test_create_compilation_result_with_workspace():
    opener = RecordingOpener([(200, {"name": "x"})])
    client = DataformClient("tok", opener=opener)
    client.create_compilation_result(REPO, workspace="ws")
    _, _, _, body = opener.calls[0]
    assert json.loads(body) == {"workspace": f"{REPO}/workspaces/ws"}

def test_query_actions_follows_pagination():
    name = f"{REPO}/compilationResults/abc"
    opener = RecordingOpener([
        (200, {"compilationResultActions": [{"filePath": "a"}], "nextPageToken": "t2"}),
        (200, {"compilationResultActions": [{"filePath": "b"}]}),
    ])
    client = DataformClient("tok", opener=opener)
    actions = client.query_actions(name)
    assert [a["filePath"] for a in actions] == ["a", "b"]
    assert opener.calls[0][1] == f"{BASE_URL}/{name}:query"
    assert "pageToken=t2" in opener.calls[1][1]

def test_non_2xx_raises_api_error():
    opener = RecordingOpener([(403, {"error": {"message": "denied"}})])
    client = DataformClient("tok", opener=opener)
    with pytest.raises(ApiError) as exc:
        client.create_compilation_result(REPO, commitish="main")
    assert "403" in str(exc.value)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_api.py -v`
Expected: FAIL (`ModuleNotFoundError`).

- [ ] **Step 3: Implement `api.py`**

```python
# src/dataform_extract/api.py
"""Minimal Dataform REST client: create a compilation result and query its actions."""
import json
import urllib.error
import urllib.request
from urllib.parse import quote

BASE_URL = "https://dataform.googleapis.com/v1beta1"


class ApiError(Exception):
    """Raised on a non-2xx response from the Dataform API."""


def _default_opener(method: str, url: str, headers: dict, body: bytes | None):
    request = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request) as response:
            return response.status, response.read()
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read()


class DataformClient:
    def __init__(self, token: str, opener=_default_opener, base_url: str = BASE_URL):
        self._token = token
        self._opener = opener
        self._base = base_url

    def _request(self, method: str, url: str, body: dict | None = None) -> dict:
        headers = {"Authorization": f"Bearer {self._token}"}
        raw_body = None
        if body is not None:
            headers["Content-Type"] = "application/json"
            raw_body = json.dumps(body).encode()
        status, payload = self._opener(method, url, headers, raw_body)
        if not 200 <= status < 300:
            raise ApiError(f"HTTP {status} from {url}: {payload.decode(errors='replace')}")
        return json.loads(payload) if payload else {}

    def create_compilation_result(self, repo: str, *, commitish: str | None = None,
                                  workspace: str | None = None) -> str:
        url = f"{self._base}/{repo}/compilationResults"
        if commitish is not None:
            body = {"gitCommitish": commitish}
        else:
            body = {"workspace": f"{repo}/workspaces/{workspace}"}
        return self._request("POST", url, body)["name"]

    def query_actions(self, compilation_result_name: str) -> list[dict]:
        actions: list[dict] = []
        page_token: str | None = None
        while True:
            url = f"{self._base}/{compilation_result_name}:query"
            if page_token:
                url += f"?pageToken={quote(page_token)}"
            data = self._request("GET", url)
            actions.extend(data.get("compilationResultActions", []))
            page_token = data.get("nextPageToken")
            if not page_token:
                return actions
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_api.py -v`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
git add src/dataform_extract/api.py tests/test_api.py
git commit -m "feat: Dataform REST client with pagination"
```

---

### Task 6: Orchestration + summary (`__main__.py`)

**Files:**
- Create: `src/dataform_extract/__main__.py`
- Test: `tests/test_main.py`

**Interfaces:**
- Consumes: `cli.parse_args`, `auth.get_access_token`, `api.DataformClient`, `ddl.reconstruct`, `writer.write_sql`, `writer.UnsafePathError`, `api.ApiError`, `auth.AuthError`.
- Produces:
  - `@dataclass(frozen=True) class Summary` with `written: int`, `skipped: int`, `warnings: int`, `incremental: int`.
  - `run(args: Args, *, token_getter=get_access_token, client_factory=DataformClient) -> Summary` — testable core; performs the full flow and returns counts (no `sys.exit`). Applies `path_filter` (prefix match on `filePath`), counts an action as `incremental` when its relation is `INCREMENTAL_TABLE`.
  - `main(argv: list[str] | None = None) -> int` — parses args, calls `run`, prints the summary; returns exit code 0 (success), 1 (`ApiError`), or 2 (`AuthError`).

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_main.py
from dataform_extract.cli import Args
from dataform_extract.__main__ import run, Summary

def make_args(tmp_path, **over):
    base = dict(repo="projects/p/locations/us/repositories/r", commitish="main",
                workspace=None, out=str(tmp_path), path_filter=None,
                include_assertions=False, include_operations=True)
    base.update(over)
    return Args(**base)

class FakeClient:
    def __init__(self, token, **kw):
        self.actions = FakeClient.ACTIONS
    def create_compilation_result(self, repo, *, commitish=None, workspace=None):
        return "cr/1"
    def query_actions(self, name):
        return self.actions

def _run(tmp_path, actions, **over):
    FakeClient.ACTIONS = actions
    return run(make_args(tmp_path, **over),
               token_getter=lambda: "tok", client_factory=FakeClient)

def test_writes_table_and_skips_declaration(tmp_path):
    actions = [
        {"filePath": "definitions/o.sqlx", "target": {"database": "p", "schema": "s", "name": "o"},
         "relation": {"relationType": "TABLE", "selectQuery": "SELECT 1"}},
        {"filePath": "definitions/d.sqlx", "target": {"database": "p", "schema": "s", "name": "d"},
         "declaration": {}},
    ]
    summary = _run(tmp_path, actions)
    assert summary == Summary(written=1, skipped=1, warnings=0, incremental=0)
    assert (tmp_path / "definitions/o.sql").read_text() == \
        "CREATE OR REPLACE TABLE `p.s.o` AS\nSELECT 1;\n"

def test_path_filter_excludes_non_matching(tmp_path):
    actions = [
        {"filePath": "definitions/marts/a.sqlx", "target": {"database": "p", "schema": "s", "name": "a"},
         "relation": {"relationType": "VIEW", "selectQuery": "SELECT 1"}},
        {"filePath": "definitions/staging/b.sqlx", "target": {"database": "p", "schema": "s", "name": "b"},
         "relation": {"relationType": "VIEW", "selectQuery": "SELECT 2"}},
    ]
    summary = _run(tmp_path, actions, path_filter="definitions/marts")
    assert summary.written == 1
    assert (tmp_path / "definitions/marts/a.sql").exists()
    assert not (tmp_path / "definitions/staging/b.sql").exists()

def test_malformed_relation_counts_as_warning(tmp_path):
    actions = [
        {"filePath": "definitions/bad.sqlx", "target": {"database": "p", "schema": "s", "name": "bad"},
         "relation": {"relationType": "TABLE"}},
    ]
    summary = _run(tmp_path, actions)
    assert summary == Summary(written=0, skipped=0, warnings=1, incremental=0)

def test_incremental_counted(tmp_path):
    actions = [
        {"filePath": "definitions/i.sqlx", "target": {"database": "p", "schema": "s", "name": "i"},
         "relation": {"relationType": "INCREMENTAL_TABLE", "selectQuery": "SELECT 1"}},
    ]
    summary = _run(tmp_path, actions)
    assert summary.written == 1 and summary.incremental == 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_main.py -v`
Expected: FAIL (`ModuleNotFoundError`).

- [ ] **Step 3: Implement `__main__.py`**

```python
# src/dataform_extract/__main__.py
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_main.py -v`
Expected: PASS (4 tests).

- [ ] **Step 5: Run the full suite**

Run: `pytest -v`
Expected: PASS (all tasks' tests green).

- [ ] **Step 6: Commit**

```bash
git add src/dataform_extract/__main__.py tests/test_main.py
git commit -m "feat: orchestration, path filtering, and summary"
```

---

### Task 7: README with usage + manual smoke test

**Files:**
- Create: `README.md`

**Interfaces:**
- Consumes: the finished CLI.
- Produces: user-facing documentation. No code / tests.

- [ ] **Step 1: Write `README.md`**

````markdown
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
````

- [ ] **Step 2: Commit**

```bash
git add README.md
git commit -m "docs: usage and manual smoke test"
```

---

## Self-Review

**Spec coverage:**
- API compile→query→mirror flow → Tasks 5, 6. ✅
- stdlib-only + gcloud auth → Task 2, Global Constraints. ✅
- `--commitish`/`--workspace` mutually exclusive → Task 1. ✅
- Path-prefix filter → Task 6. ✅
- Runnable DDL per type (table/view/mat-view/incremental/operations/assertion/declaration) → Task 3. ✅
- Traversal-safe writes under `--out` → Task 4. ✅
- Error handling / exit codes (auth=2, api=1, warn+skip malformed) → Tasks 2, 6. ✅
- Summary output → Task 6. ✅
- Unit + stubbed-integration tests, no live API, README smoke test → all tasks + Task 7. ✅

**Placeholder scan:** No TBD/TODO/"handle edge cases"; every code and test step is concrete. ✅

**Type consistency:** `Args` fields, `reconstruct(...)` signature, `DataformClient` opener signature, `Summary` fields, and `write_sql`/`output_path` names are used identically across Tasks 1–7. ✅
