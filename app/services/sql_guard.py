"""SQL safety guard for analytics queries.

Defense-in-depth:
  Layer 1 — sqlglot AST parse: only single SELECT statements allowed.
  Layer 2 — keyword block list: no DML/DDL keywords.
  Layer 3 — table whitelist: only the three orchestrator tables.
  Layer 4 — LIMIT injection: auto-add LIMIT if missing and non-aggregate.
  Layer 5 — read-only DB engine: even a bypass can't write (no grants).
"""

from __future__ import annotations

import logging
import re

import sqlglot
import sqlglot.expressions as exp

logger = logging.getLogger(__name__)

# Tables the analytics RO user may query
WHITELISTED_TABLES: frozenset[str] = frozenset(
    {"devin_runs", "devin_events", "analytics_queries"}
)

# Keywords that must never appear anywhere in the query
BLOCKED_KEYWORDS: frozenset[str] = frozenset(
    {
        "insert",
        "update",
        "delete",
        "drop",
        "alter",
        "truncate",
        "create",
        "copy",
        "grant",
        "revoke",
        "execute",
        "exec",
        "call",
        "merge",
        "replace",
        "load",
        "import",
    }
)

DEFAULT_LIMIT = 500


class SQLGuardError(ValueError):
    """Raised when a query fails the safety check."""


def validate_and_sanitize(sql: str, default_limit: int = DEFAULT_LIMIT) -> str:
    """Validate SQL safety and return a sanitized version with LIMIT injected.

    Raises SQLGuardError on any violation.
    """
    if not sql or not sql.strip():
        raise SQLGuardError("Empty query.")

    # Layer 2: keyword block (fast pre-check before parse overhead)
    sql_lower = sql.lower()
    for kw in BLOCKED_KEYWORDS:
        # Use word-boundary to avoid false positives (e.g. "created_at" contains "create"
        # but preceded by a letter — however we want to catch "create table" not "created")
        if re.search(r"\b" + re.escape(kw) + r"\b", sql_lower):
            raise SQLGuardError(f"Blocked keyword detected: {kw!r}")

    # Block multiple statements (semicolon injection)
    # Allow a trailing semicolon but not multiple
    stripped = sql.rstrip().rstrip(";")
    if ";" in stripped:
        raise SQLGuardError("Multiple statements are not allowed.")

    # Layer 1: AST parse
    try:
        statements = sqlglot.parse(sql, dialect="postgres")
    except sqlglot.errors.ParseError as exc:
        raise SQLGuardError(f"SQL parse error: {exc}") from exc

    if not statements:
        raise SQLGuardError("No parseable statements found.")
    if len(statements) > 1:
        raise SQLGuardError("Only a single SELECT statement is allowed.")

    stmt = statements[0]
    if not isinstance(stmt, exp.Select):
        raise SQLGuardError(
            f"Only SELECT statements are allowed; got {type(stmt).__name__}."
        )

    # Layer 3: table whitelist
    referenced = {
        tbl.name.lower()
        for tbl in stmt.find_all(exp.Table)
        if tbl.name  # skip subquery aliases
    }
    disallowed = referenced - WHITELISTED_TABLES
    if disallowed:
        raise SQLGuardError(
            f"Query references non-whitelisted table(s): {disallowed}. "
            f"Allowed: {WHITELISTED_TABLES}"
        )

    # Layer 4: LIMIT injection
    # Aggregate queries (no GROUP BY, single COUNT/SUM/AVG) don't need LIMIT
    has_limit = stmt.find(exp.Limit) is not None
    has_group_by = stmt.find(exp.Group) is not None
    agg_funcs = list(stmt.find_all(exp.AggFunc))
    is_pure_aggregate = agg_funcs and not has_group_by

    if not has_limit and not is_pure_aggregate:
        # Inject LIMIT at the end of the SQL string (simpler than AST mutation)
        sanitized = sql.rstrip().rstrip(";") + f" LIMIT {default_limit}"
    else:
        sanitized = sql

    return sanitized
