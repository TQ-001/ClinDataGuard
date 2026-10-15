"""
tests/test_validator.py
pytest test suite for ClinDataGuard.

Covers:
  1. Valid data produces zero issues
  2. Missing required column is flagged (RULE-MISSING-COL)
  3. Duplicate patient IDs are flagged (RULE-DUPLICATE-ID)
  4. Out-of-range numeric value is flagged (RULE-RANGE)
  5. Invalid category value is flagged (RULE-CATEGORY)
  6. Date order violation is flagged (RULE-DATE-ORDER)
  7. Known alias is resolved to canonical name
  8. Alias collision raises AliasCollisionError
  9. Missing required cell value is flagged (RULE-MISSING-VAL)
 10. Type error is flagged (RULE-TYPE-ERROR)
 11. Empty DataFrame returns no issues
 12. Fixed-seed generation is reproducible (determinism)
 13. Generated sample dataset contains expected injected defects
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import pytest

# Ensure project root is on path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.generator import (
    DATE_INVERSION_ROWS,
    DUPLICATE_ID_ROWS,
    INVALID_AGE_ROWS,
    INVALID_SEX_ROWS,
    generate_dataset,
)
from src.schema import AliasCollisionError, load, resolve_aliases
from src.validator import (
    RULE_CATEGORY,
    RULE_DATE_ORDER,
    RULE_DUPLICATE_ID,
    RULE_MISSING_COL,
    RULE_MISSING_VAL,
    RULE_RANGE,
    RULE_TYPE_ERROR,
    validate,
)

SCHEMA_PATH = Path(__file__).parent.parent / "config" / "schema.yaml"


@pytest.fixture(scope="module")
def schema():
    return load(SCHEMA_PATH)


@pytest.fixture
def clean_df():
    """A minimal valid 3-row DataFrame with all required fields."""
    return pd.DataFrame(
        {
            "patient_id": ["PAT001", "PAT002", "PAT003"],
            "age": [45, 60, 38],
            "sex": ["Male", "Female", "Other"],
            "bmi": [24.5, 30.1, 22.0],
            "smoking_status": ["Never", "Former", "Current"],
            "pack_years": [0.0, 20.0, 15.0],
            "fev1_percent_predicted": [85.0, 70.0, 95.0],
            "baseline_cvd": ["No", "Yes", "No"],
            "ct_date": ["2021-01-15", "2020-06-01", "2022-03-10"],
            "followup_date": ["2022-01-15", "2021-06-01", "2023-03-10"],
        }
    )


# ── Test 1: Valid data produces zero issues ───────────────────────────────────
def test_valid_data_no_issues(clean_df, schema):
    issues = validate(clean_df, schema)
    assert issues == [], f"Expected no issues on clean data, got: {issues}"


# ── Test 2: Missing required column ──────────────────────────────────────────
def test_missing_required_column(clean_df, schema):
    df = clean_df.drop(columns=["age"])
    issues = validate(df, schema)
    rule_ids = [i.rule_id for i in issues]
    assert RULE_MISSING_COL in rule_ids
    missing_col_issues = [i for i in issues if i.rule_id == RULE_MISSING_COL]
    assert any(i.column == "age" for i in missing_col_issues)


# ── Test 3: Duplicate patient IDs ────────────────────────────────────────────
def test_duplicate_patient_ids(clean_df, schema):
    df = clean_df.copy()
    df.at[2, "patient_id"] = "PAT001"  # duplicate of row 0
    issues = validate(df, schema)
    dup_issues = [i for i in issues if i.rule_id == RULE_DUPLICATE_ID]
    assert len(dup_issues) >= 1
    assert any(i.patient_id == "PAT001" for i in dup_issues)


# ── Test 4: Out-of-range numeric value ───────────────────────────────────────
def test_out_of_range_age(clean_df, schema):
    df = clean_df.copy()
    df.at[1, "age"] = 150  # > max 120
    issues = validate(df, schema)
    range_issues = [i for i in issues if i.rule_id == RULE_RANGE and i.column == "age"]
    assert len(range_issues) == 1
    assert "150" in range_issues[0].observed_value


def test_out_of_range_bmi(clean_df, schema):
    df = clean_df.copy()
    df.at[0, "bmi"] = 5.0  # < min 10.0
    issues = validate(df, schema)
    range_issues = [i for i in issues if i.rule_id == RULE_RANGE and i.column == "bmi"]
    assert len(range_issues) == 1


# ── Test 5: Invalid category value ───────────────────────────────────────────
def test_invalid_sex_category(clean_df, schema):
    df = clean_df.copy()
    df.at[0, "sex"] = "Unknown"
    issues = validate(df, schema)
    cat_issues = [i for i in issues if i.rule_id == RULE_CATEGORY and i.column == "sex"]
    assert len(cat_issues) == 1
    assert cat_issues[0].observed_value == "Unknown"


def test_invalid_smoking_status(clean_df, schema):
    df = clean_df.copy()
    df.at[1, "smoking_status"] = "Occasional"
    issues = validate(df, schema)
    cat_issues = [i for i in issues if i.rule_id == RULE_CATEGORY and i.column == "smoking_status"]
    assert len(cat_issues) == 1


# ── Test 6: Date order violation ─────────────────────────────────────────────
def test_followup_before_ct_date(clean_df, schema):
    df = clean_df.copy()
    df.at[0, "followup_date"] = "2020-12-31"  # before ct_date 2021-01-15
    issues = validate(df, schema)
    date_issues = [i for i in issues if i.rule_id == RULE_DATE_ORDER]
    assert len(date_issues) == 1
    assert date_issues[0].row_number == 1


def test_followup_equal_to_ct_date(clean_df, schema):
    """followup_date equal to ct_date should also be flagged (must be strictly after)."""
    df = clean_df.copy()
    df.at[0, "followup_date"] = df.at[0, "ct_date"]
    issues = validate(df, schema)
    date_issues = [i for i in issues if i.rule_id == RULE_DATE_ORDER]
    assert len(date_issues) == 1


# ── Test 7: Alias resolution ─────────────────────────────────────────────────
def test_alias_resolution_fev1(clean_df, schema):
    """fev1_pp is a known alias and should be resolved to fev1_percent_predicted."""
    df = clean_df.rename(columns={"fev1_percent_predicted": "fev1_pp"})
    df_resolved = resolve_aliases(df, schema)
    assert "fev1_percent_predicted" in df_resolved.columns
    assert "fev1_pp" not in df_resolved.columns


def test_alias_resolution_age(clean_df, schema):
    """age_years is a known alias for age."""
    df = clean_df.rename(columns={"age": "age_years"})
    df_resolved = resolve_aliases(df, schema)
    assert "age" in df_resolved.columns
    issues = validate(df_resolved, schema)
    # Should still produce no issues on clean data
    assert all(i.rule_id != RULE_MISSING_COL for i in issues), \
        "age column should be present after alias resolution"


# ── Test 8: Alias collision raises error ─────────────────────────────────────
def test_alias_collision_raises(clean_df, schema):
    """Having both 'age' and 'age_years' in the same DataFrame is a collision."""
    df = clean_df.copy()
    df["age_years"] = df["age"]  # now two columns resolve to 'age'
    with pytest.raises(AliasCollisionError) as exc_info:
        resolve_aliases(df, schema)
    assert "age" in str(exc_info.value)


# ── Test 9: Missing required cell value ──────────────────────────────────────
def test_missing_required_cell(clean_df, schema):
    import numpy as np

    df = clean_df.copy()
    df.at[1, "age"] = np.nan  # age is required
    issues = validate(df, schema)
    missing_val_issues = [i for i in issues if i.rule_id == RULE_MISSING_VAL and i.column == "age"]
    assert len(missing_val_issues) == 1
    assert missing_val_issues[0].row_number == 2  # 1-based


# ── Test 10: Type error ───────────────────────────────────────────────────────
def test_type_error_non_numeric_age(clean_df, schema):
    df = clean_df.copy()
    df["age"] = df["age"].astype(object)   # allow mixed types; avoid FutureWarning
    df.at[0, "age"] = "forty-five"
    issues = validate(df, schema)
    type_issues = [i for i in issues if i.rule_id == RULE_TYPE_ERROR and i.column == "age"]
    assert len(type_issues) == 1


def test_type_error_invalid_date(clean_df, schema):
    df = clean_df.copy()
    df.at[0, "ct_date"] = "not-a-date"
    issues = validate(df, schema)
    type_issues = [i for i in issues if i.rule_id == RULE_TYPE_ERROR and i.column == "ct_date"]
    assert len(type_issues) == 1


# ── Test 11: Empty DataFrame (no columns) ────────────────────────────────────
def test_empty_dataframe_no_issues(schema):
    """A completely structureless DataFrame (no columns) returns no issues."""
    df = pd.DataFrame()
    issues = validate(df, schema)
    assert issues == []


def test_header_only_csv_flags_missing_columns(schema):
    """A CSV with column headers but zero data rows should still flag absent required columns."""
    import io as _io
    df = pd.read_csv(_io.StringIO("patient_id,age,sex,bmi\n"))
    assert len(df) == 0 and len(df.columns) > 0, "fixture should have columns but no rows"
    issues = validate(df, schema)
    mc = [i for i in issues if i.rule_id == RULE_MISSING_COL]
    # fev1_percent_predicted, smoking_status, baseline_cvd, ct_date, followup_date are absent
    missing_names = {i.column for i in mc}
    assert "fev1_percent_predicted" in missing_names
    assert "smoking_status" in missing_names
    assert "ct_date" in missing_names


# ── Test 12: Reproducible generation ─────────────────────────────────────────
def test_generation_is_reproducible():
    df1 = generate_dataset(n=100, seed=42)
    df2 = generate_dataset(n=100, seed=42)
    pd.testing.assert_frame_equal(df1, df2)


def test_different_seeds_differ():
    df1 = generate_dataset(n=100, seed=42)
    df2 = generate_dataset(n=100, seed=99)
    assert not df1.equals(df2)


# ── Test 13: Injected defects are present in generated sample ─────────────────
def test_generated_dataset_has_duplicate_ids(schema):
    df = generate_dataset()
    df_resolved = resolve_aliases(df, schema)
    issues = validate(df_resolved, schema)
    dup_issues = [i for i in issues if i.rule_id == RULE_DUPLICATE_ID]
    assert len(dup_issues) >= len(DUPLICATE_ID_ROWS), \
        f"Expected at least {len(DUPLICATE_ID_ROWS)} duplicate ID issues, got {len(dup_issues)}"


def test_generated_dataset_has_date_inversions(schema):
    df = generate_dataset()
    df_resolved = resolve_aliases(df, schema)
    issues = validate(df_resolved, schema)
    date_issues = [i for i in issues if i.rule_id == RULE_DATE_ORDER]
    assert len(date_issues) >= len(DATE_INVERSION_ROWS), \
        f"Expected at least {len(DATE_INVERSION_ROWS)} date order issues, got {len(date_issues)}"


def test_generated_dataset_has_invalid_sex(schema):
    df = generate_dataset()
    df_resolved = resolve_aliases(df, schema)
    issues = validate(df_resolved, schema)
    sex_issues = [i for i in issues if i.rule_id == RULE_CATEGORY and i.column == "sex"]
    assert len(sex_issues) >= len(INVALID_SEX_ROWS)


def test_generated_dataset_has_out_of_range_age(schema):
    df = generate_dataset()
    df_resolved = resolve_aliases(df, schema)
    issues = validate(df_resolved, schema)
    age_range_issues = [i for i in issues if i.rule_id == RULE_RANGE and i.column == "age"]
    assert len(age_range_issues) >= len(INVALID_AGE_ROWS)
