"""
src/validator.py
Pure-Python validation engine for ClinDataGuard.

Usage (without UI):
    from src.schema import load, resolve_aliases
    from src.validator import validate

    schema = load()
    df_clean = resolve_aliases(df_raw, schema)
    issues = validate(df_clean, schema)
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

import pandas as pd

logger = logging.getLogger(__name__)

# ── Rule IDs ──────────────────────────────────────────────────────────────────
RULE_MISSING_COL = "RULE-MISSING-COL"
RULE_MISSING_VAL = "RULE-MISSING-VAL"
RULE_TYPE_ERROR = "RULE-TYPE-ERROR"
RULE_RANGE = "RULE-RANGE"
RULE_CATEGORY = "RULE-CATEGORY"
RULE_DUPLICATE_ID = "RULE-DUPLICATE-ID"
RULE_DATE_ORDER = "RULE-DATE-ORDER"

SEVERITY_ERROR = "error"
SEVERITY_WARNING = "warning"


@dataclass
class Issue:
    """Represents a single data quality issue found during validation."""

    row_number: int          # 1-based row number in the original CSV (0 = dataset-level)
    patient_id: str | None   # patient_id from that row, if available
    column: str              # column name where the issue was found
    rule_id: str             # identifier of the violated rule
    severity: str            # "error" or "warning"
    observed_value: str      # string representation of the bad value
    explanation: str         # human-readable explanation

    def to_dict(self) -> dict[str, Any]:
        return {
            "row_number": self.row_number,
            "patient_id": self.patient_id,
            "column": self.column,
            "rule_id": self.rule_id,
            "severity": self.severity,
            "observed_value": self.observed_value,
            "explanation": self.explanation,
        }


def _get_pid(df: pd.DataFrame, idx: int) -> str | None:
    """Safely retrieve patient_id for a row index."""
    if "patient_id" in df.columns:
        val = df.at[idx, "patient_id"]
        if pd.notna(val):
            return str(val)
    return None


def _try_cast_numeric(value: Any, dtype: str) -> tuple[bool, float | int | None]:
    """
    Attempt to cast a value to the declared numeric type.
    Returns (success, cast_value).
    """
    try:
        if dtype == "integer":
            # Accept floats that are whole numbers (e.g. 42.0 → 42)
            f = float(value)
            if f != int(f):
                return False, None
            return True, int(f)
        elif dtype == "float":
            return True, float(value)
    except (ValueError, TypeError):
        pass
    return False, None


def _try_parse_date(value: Any) -> tuple[bool, pd.Timestamp | None]:
    """Attempt to parse a value as a date. Returns (success, timestamp)."""
    if pd.isna(value):
        return False, None
    try:
        ts = pd.Timestamp(value)
        return True, ts
    except Exception:
        return False, None


# ── Validation rules ──────────────────────────────────────────────────────────

def _check_missing_columns(
    df: pd.DataFrame,
    schema: dict,
) -> list[Issue]:
    """RULE-MISSING-COL: Required columns absent from the dataset."""
    issues: list[Issue] = []
    for col_name, field_def in schema["fields"].items():
        if field_def.get("required", False) and col_name not in df.columns:
            issues.append(
                Issue(
                    row_number=0,
                    patient_id=None,
                    column=col_name,
                    rule_id=RULE_MISSING_COL,
                    severity=SEVERITY_ERROR,
                    observed_value="<absent>",
                    explanation=f"Required column '{col_name}' is missing from the dataset.",
                )
            )
    return issues


def _check_duplicate_ids(df: pd.DataFrame) -> list[Issue]:
    """RULE-DUPLICATE-ID: Duplicate patient_id values."""
    issues: list[Issue] = []
    if "patient_id" not in df.columns:
        return issues

    seen: dict[str, int] = {}
    for idx in df.index:
        pid = df.at[idx, "patient_id"]
        if pd.isna(pid):
            continue
        pid_str = str(pid)
        if pid_str in seen:
            issues.append(
                Issue(
                    row_number=idx + 1,
                    patient_id=pid_str,
                    column="patient_id",
                    rule_id=RULE_DUPLICATE_ID,
                    severity=SEVERITY_ERROR,
                    observed_value=pid_str,
                    explanation=(
                        f"Duplicate patient_id '{pid_str}' also appears at row {seen[pid_str]}."
                    ),
                )
            )
        else:
            seen[pid_str] = idx + 1

    return issues


def _check_row(
    df: pd.DataFrame,
    idx: int,
    schema: dict,
) -> list[Issue]:
    """
    Check a single row for RULE-MISSING-VAL, RULE-TYPE-ERROR, RULE-RANGE,
    RULE-CATEGORY, and RULE-DATE-ORDER.
    """
    issues: list[Issue] = []
    row_number = idx + 1
    pid = _get_pid(df, idx)

    col_dates: dict[str, pd.Timestamp] = {}  # store parsed dates for order check

    for col_name, field_def in schema["fields"].items():
        if col_name not in df.columns:
            continue  # missing columns already flagged at dataset level

        raw_value = df.at[idx, col_name]
        dtype = field_def.get("type", "string")
        required = field_def.get("required", False)

        # ── RULE-MISSING-VAL ────────────────────────────────────────────────
        is_null = pd.isna(raw_value) if not isinstance(raw_value, str) else (raw_value.strip() == "")
        if is_null:
            if required:
                issues.append(
                    Issue(
                        row_number=row_number,
                        patient_id=pid,
                        column=col_name,
                        rule_id=RULE_MISSING_VAL,
                        severity=SEVERITY_ERROR,
                        observed_value="<null>",
                        explanation=f"Required field '{col_name}' is null/empty.",
                    )
                )
            continue  # can't do further checks on null

        # ── Type & value checks ─────────────────────────────────────────────
        observed_str = str(raw_value)

        if dtype in ("integer", "float"):
            ok, cast_val = _try_cast_numeric(raw_value, dtype)
            if not ok:
                issues.append(
                    Issue(
                        row_number=row_number,
                        patient_id=pid,
                        column=col_name,
                        rule_id=RULE_TYPE_ERROR,
                        severity=SEVERITY_ERROR,
                        observed_value=observed_str,
                        explanation=(
                            f"'{col_name}' expects {dtype} but got '{observed_str}'."
                        ),
                    )
                )
                continue

            # ── RULE-RANGE ──────────────────────────────────────────────────
            range_def = field_def.get("range")
            if range_def and cast_val is not None:
                lo = range_def.get("min")
                hi = range_def.get("max")
                out_of_range = (lo is not None and cast_val < lo) or (
                    hi is not None and cast_val > hi
                )
                if out_of_range:
                    issues.append(
                        Issue(
                            row_number=row_number,
                            patient_id=pid,
                            column=col_name,
                            rule_id=RULE_RANGE,
                            severity=SEVERITY_ERROR,
                            observed_value=observed_str,
                            explanation=(
                                f"'{col_name}' value {cast_val} is outside "
                                f"allowed range [{lo}, {hi}]."
                            ),
                        )
                    )

        elif dtype == "string":
            # ── RULE-CATEGORY ────────────────────────────────────────────────
            categories = field_def.get("categories")
            if categories:
                if str(raw_value) not in categories:
                    issues.append(
                        Issue(
                            row_number=row_number,
                            patient_id=pid,
                            column=col_name,
                            rule_id=RULE_CATEGORY,
                            severity=SEVERITY_ERROR,
                            observed_value=observed_str,
                            explanation=(
                                f"'{col_name}' value '{raw_value}' is not in "
                                f"allowed categories {categories}."
                            ),
                        )
                    )

        elif dtype == "date":
            ok, ts = _try_parse_date(raw_value)
            if not ok:
                issues.append(
                    Issue(
                        row_number=row_number,
                        patient_id=pid,
                        column=col_name,
                        rule_id=RULE_TYPE_ERROR,
                        severity=SEVERITY_ERROR,
                        observed_value=observed_str,
                        explanation=f"'{col_name}' value '{raw_value}' is not a valid date.",
                    )
                )
            else:
                col_dates[col_name] = ts  # type: ignore[assignment]

    # ── RULE-DATE-ORDER ──────────────────────────────────────────────────────
    if "ct_date" in col_dates and "followup_date" in col_dates:
        ct = col_dates["ct_date"]
        fu = col_dates["followup_date"]
        if fu <= ct:
            issues.append(
                Issue(
                    row_number=row_number,
                    patient_id=pid,
                    column="followup_date",
                    rule_id=RULE_DATE_ORDER,
                    severity=SEVERITY_ERROR,
                    observed_value=str(df.at[idx, "followup_date"]),
                    explanation=(
                        f"followup_date ({fu.date()}) must be after "
                        f"ct_date ({ct.date()})."
                    ),
                )
            )

    return issues


# ── Public API ────────────────────────────────────────────────────────────────

def validate(df: pd.DataFrame, schema: dict) -> list[Issue]:
    """
    Validate a DataFrame against the schema.

    The DataFrame should already have canonical column names
    (i.e., alias resolution has been applied). This function
    never modifies the input DataFrame.

    Parameters
    ----------
    df : pd.DataFrame
        Dataset to validate.
    schema : dict
        Parsed schema (result of ``schema.load()``).

    Returns
    -------
    list[Issue]
        All detected data quality issues. Empty list if data is clean.
    """
    # A completely structureless object (no columns at all) → nothing to check.
    if df.empty and len(df.columns) == 0:
        logger.info("Empty DataFrame (no columns) passed to validator; returning no issues.")
        return []

    issues: list[Issue] = []

    # 1. Dataset-level checks – run even when there are 0 data rows so that
    #    a header-only CSV still reports absent required columns.
    issues.extend(_check_missing_columns(df, schema))
    issues.extend(_check_duplicate_ids(df))

    # 2. Row-level checks (skipped naturally when df has 0 rows)
    for idx in df.index:
        issues.extend(_check_row(df, idx, schema))

    logger.info("Validation complete: %d issues found in %d rows.", len(issues), len(df))
    return issues
