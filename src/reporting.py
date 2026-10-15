"""
src/reporting.py
Export data quality issues as CSV and JSON summaries.
"""
from __future__ import annotations

import io
import json
import logging
from pathlib import Path
from typing import Any

import pandas as pd

from src.validator import Issue

logger = logging.getLogger(__name__)


def issues_to_dataframe(issues: list[Issue]) -> pd.DataFrame:
    """
    Convert a list of Issue objects to a pandas DataFrame.

    Parameters
    ----------
    issues : list[Issue]
        Issues returned by ``validate()``.

    Returns
    -------
    pd.DataFrame
        One row per issue with columns matching the Issue fields.
    """
    if not issues:
        return pd.DataFrame(
            columns=[
                "row_number",
                "patient_id",
                "column",
                "rule_id",
                "severity",
                "observed_value",
                "explanation",
            ]
        )
    return pd.DataFrame([i.to_dict() for i in issues])


def issues_to_csv(
    issues: list[Issue],
    path: str | Path | None = None,
) -> str:
    """
    Serialize issues to CSV.

    Parameters
    ----------
    issues : list[Issue]
        Issues to export.
    path : str or Path, optional
        If given, write to this file. Otherwise return the CSV as a string.

    Returns
    -------
    str
        CSV content (always returned; also written to file if path provided).
    """
    df = issues_to_dataframe(issues)
    buffer = io.StringIO()
    df.to_csv(buffer, index=False)
    csv_str = buffer.getvalue()

    if path is not None:
        out = Path(path)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(csv_str, encoding="utf-8")
        logger.info("Issues CSV written to %s (%d rows)", out, len(issues))

    return csv_str


def summary_to_json(
    df: pd.DataFrame,
    issues: list[Issue],
    path: str | Path | None = None,
) -> str:
    """
    Build a JSON summary of validation results.

    Parameters
    ----------
    df : pd.DataFrame
        The validated DataFrame (used to report total row count).
    issues : list[Issue]
        Issues returned by ``validate()``.
    path : str or Path, optional
        If given, write JSON to this file. Otherwise return as a string.

    Returns
    -------
    str
        JSON string (always returned; also written to file if path provided).
    """
    issues_by_severity: dict[str, int] = {}
    issues_by_rule: dict[str, int] = {}

    for issue in issues:
        issues_by_severity[issue.severity] = issues_by_severity.get(issue.severity, 0) + 1
        issues_by_rule[issue.rule_id] = issues_by_rule.get(issue.rule_id, 0) + 1

    summary: dict[str, Any] = {
        "total_rows": len(df),
        "total_issues": len(issues),
        "issues_by_severity": issues_by_severity,
        "issues_by_rule": issues_by_rule,
    }

    json_str = json.dumps(summary, indent=2)

    if path is not None:
        out = Path(path)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json_str, encoding="utf-8")
        logger.info("Summary JSON written to %s", out)

    return json_str
