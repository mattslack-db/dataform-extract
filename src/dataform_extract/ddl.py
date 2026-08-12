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
    statements.append(_terminate(f"CREATE OR REPLACE {keyword} {ref} AS\n{select_query.strip()}"))
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
        return "\n\n".join(_terminate(q) for q in queries) or None
    if "assertion" in action:
        if not include_assertions:
            return None
        select_query = action["assertion"].get("selectQuery", "")
        return f"-- Assertion (expects zero rows): {ref}\n{_terminate(select_query)}"

    raise ValueError(f"unrecognized action shape for {ref}: keys={sorted(action)}")
