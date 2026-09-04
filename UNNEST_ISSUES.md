# BigQuery `UNNEST` and Lakebridge — Known Conversion Gap

**Status:** Not a `dataform-extract` bug. `dataform-extract` faithfully emits BigQuery
SQL (including `UNNEST`); the defect is downstream, in Lakebridge's transpiler engine
(sqlglot). This document records the root cause, evidence, and mitigations.

**Last investigated:** 2026-09-02 (Lakebridge `main` pinning `sqlglot==28.5.0`).

---

## TL;DR

- `dataform-extract` correctly reconstructs runnable BigQuery DDL, `UNNEST` and all.
- When that SQL is transpiled by **Lakebridge** to Databricks SQL, some `UNNEST`
  patterns are **silently mistranslated** — no error, just wrong results.
- The most dangerous surviving bug: **`LEFT JOIN UNNEST(...)` → inner
  `LATERAL VIEW EXPLODE`** instead of `LATERAL VIEW OUTER EXPLODE`, which
  **silently drops rows where the array is empty or NULL**.
- Root cause is two layers deep: (1) Lakebridge routes BigQuery through the
  **uncustomized stock sqlglot** dialect, and (2) stock sqlglot's BigQuery→Databricks
  generator has genuine `UNNEST` bugs.
- **Mitigation:** BigQuery is a first-class **reconcile** source in Lakebridge (unlike
  transpile). Use `reconcile` to catch the resulting row-count/data drift.

---

## What `UNNEST` does (BigQuery)

BigQuery has first-class `ARRAY`/`STRUCT` columns. `UNNEST` flattens an array into
rows so you can join against it (a correlated cross join):

```sql
SELECT o.order_id, item.sku, item.qty
FROM orders AS o,
  UNNEST(o.line_items) AS item        -- one row per array element
```

The Databricks/Spark equivalent is `LATERAL VIEW explode(...)` (or `explode` /
`posexplode` in a `SELECT`). Empty/NULL-array and offset semantics matter — see below.

---

## Root cause

### Layer 1 — Lakebridge treats BigQuery as a second-class *transpile* source

In `src/databricks/labs/lakebridge/transpiler/sqlglot/dialect_utils.py`, most source
dialects map to Lakebridge's **own customized parser classes**, but BigQuery maps to
the **stock sqlglot dialect** with no Lakebridge-specific handling:

```python
SQLGLOT_DIALECTS = {
    ...
    "bigquery": Dialects.BIGQUERY,   # <-- stock sqlglot, NO Lakebridge customization
    "oracle":   oracle.Oracle,       # custom parser
    "presto":   presto.Presto,       # custom parser (holds the UNNEST->LATERAL VIEW fix, issue #1209)
    "snowflake":snowflake.Snowflake, # custom parser
    "tsql":     tsql.Tsql,           # custom parser
    ...
}
```

Consequences:

- The Presto `UNNEST` cross-join → `LATERAL VIEW EXPLODE` fix (Lakebridge issue #1209)
  lives in the **Presto** parser and does **not** apply to BigQuery.
- BigQuery is **not on Lakebridge's officially supported transpile-dialect list**
  (mssql, mysql, netezza, oracle, postgresql, redshift, snowflake, synapse, teradata).
- All BigQuery work in the Lakebridge repo is on the **profiler / reconcile** side,
  not transpile — so BigQuery transpile has **no test coverage**.

### Layer 2 — stock sqlglot's BigQuery→Databricks generator has `UNNEST` bugs

Whatever stock sqlglot produces is what you get, untested. Two concrete bugs (see
evidence). One is fixed by a version bump; one persists in the latest.

---

## Evidence (reproducible)

```python
import sqlglot
for sql in [
    "SELECT o.order_id, item.sku FROM orders AS o, UNNEST(o.line_items) AS item",
    "SELECT n, idx FROM UNNEST([1,2,3]) AS n WITH OFFSET AS idx",
    "SELECT o.order_id, item.sku FROM orders AS o LEFT JOIN UNNEST(o.line_items) AS item ON TRUE",
]:
    print(sqlglot.transpile(sql, read="bigquery", write="databricks")[0])
```

| BigQuery input | sqlglot 26.1.3 (old pin) | sqlglot 28.5.0 (current pin) | Correct? |
|---|---|---|---|
| `FROM t, UNNEST(arr) AS x` | `LATERAL VIEW EXPLODE(arr) AS x` | `LATERAL VIEW EXPLODE(arr) AS x` | ✅ fine |
| `UNNEST(arr) WITH OFFSET AS idx` | `POSEXPLODE(...) AS _t0(n)` — **idx dropped; `n` binds to position, not value** | `POSEXPLODE(...) AS _t0(idx, n)` | ✅ **fixed by upgrade** |
| `LEFT JOIN UNNEST(arr) ON TRUE` | `LATERAL VIEW EXPLODE(arr)` (inner) | `LATERAL VIEW EXPLODE(arr)` (inner) | ❌ **still broken** |

### The dangerous survivor: `LEFT JOIN UNNEST` loses `OUTER`

BigQuery's `LEFT JOIN UNNEST(arr)` (and correlated `UNNEST` in outer contexts)
**preserves** rows where `arr` is empty or NULL. The correct Databricks output is
`LATERAL VIEW OUTER EXPLODE(arr)`. sqlglot emits plain (inner) `EXPLODE`, which
**drops those rows**. No error is raised — row counts just silently shrink.

---

## Impact on the pipeline

- **`WITH OFFSET` bug:** already gone if Lakebridge is current (sqlglot 28.5.0). If your
  Lakebridge is pinned to sqlglot 26.x, upgrading fixes it.
- **`LEFT/OUTER JOIN UNNEST` bug:** persists in the latest sqlglot; needs an upstream
  fix or manual patching of the transpiled output.
- **Plain `FROM t, UNNEST(arr)` and `CROSS JOIN UNNEST`:** transpile correctly. This is
  why the failure is insidious — it works often enough to look trustworthy.

---

## Mitigations

1. **Use Lakebridge `reconcile` as a validation gate.** BigQuery *is* a first-class
   reconcile source (unlike transpile). Reconciling the BigQuery source against the
   Databricks target catches exactly this class of silent row-count/data drift.
2. **Manually patch outer-join `UNNEST`.** After transpiling, search the output for
   `LATERAL VIEW EXPLODE` that originated from a `LEFT JOIN UNNEST` / outer context and
   change it to `LATERAL VIEW OUTER EXPLODE`.
3. **Ensure a current sqlglot** (≥ 28.x) under Lakebridge to clear the `WITH OFFSET` bug.

---

## Analyzer coverage (does *not* detect this)

The Lakebridge **Analyzer** (`databricks labs lakebridge analyze --source-tech bigquery`,
implemented via `databricks.labs.bladespector`) is a separate component from the
transpiler. It scans a **folder of source files** — exactly what `dataform-extract`
produces — and writes an Excel/JSON report with complexity scores, a job/object
inventory, and interdependency mapping. It does **not** transpile, so the silent
`UNNEST` mistranslation cannot occur *in* the Analyzer.

However, the Analyzer is **not a detection mechanism** for this bug:

- **BigQuery is supported** by the Analyzer (it's on the Analyzer's supported-dialect
  list, unlike the transpiler's). It reads `UNNEST`-containing files without error.
- Its SQL complexity scoring is **regex/pattern-based statement counting**, keyed only
  on loop count, statement counts, **PIVOT**, and **XML**. `UNNEST` is **not** a scored
  signal.
- Consequently, a `UNNEST`-heavy but otherwise simple BigQuery object typically scores
  **LOW/MEDIUM** ("transpile directly, little manual review expected") — the opposite of
  the caution it actually needs.

**Net:** the Analyzer is useful for sizing/inventory, but it will not flag `UNNEST` as a
risk. Detection still relies on **reconcile** (row-count/data parity), which is a
first-class BigQuery feature.

---

## Upstream reports (two distinct targets)

- **`tobymao/sqlglot`** — BigQuery→Databricks/Spark generator drops outer-join
  semantics: `LEFT JOIN UNNEST(arr) ON TRUE` should emit `LATERAL VIEW OUTER EXPLODE`,
  currently emits inner `EXPLODE` (silent row loss). Reproduces with plain sqlglot,
  no Lakebridge involved. Still present in 28.5.0.
- **`databrickslabs/lakebridge`** — BigQuery is an uncustomized, untested transpile
  source (maps to stock `Dialects.BIGQUERY`, not on the supported-dialect list, no
  transpile test coverage). Either add BigQuery to the tested matrix with custom
  `UNNEST` handling, or document BigQuery transpile as experimental/unsupported.

---

## References

- Lakebridge transpile dialect map: `transpiler/sqlglot/dialect_utils.py`
- Lakebridge issue #1209 — "Handling presto Unnest cross join to Databricks lateral
  view" (the Presto-only fix that does not cover BigQuery)
- Lakebridge supported transpile dialects (docs): mssql, mysql, netezza, oracle,
  postgresql, redshift, snowflake, synapse, teradata — **no bigquery**
- sqlglot pin in Lakebridge `main`: `sqlglot==28.5.0`
