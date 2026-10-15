"""
src/generator.py
Reproducible synthetic clinical dataset generator for ClinDataGuard.

Generates 1000 fictional patients with intentionally injected data quality
defects that are documented here and verified by tests.

Injected defects (fixed positions using seed=42):
  - 5 duplicate patient IDs (rows 10–14 share IDs with rows 0–4)
  - ~3% missing values scattered across age, bmi, pack_years, fev1_percent_predicted
  - 8 out-of-range ages (< 0 or > 120) at rows 20–27
  - 10 invalid sex categories ('Unknown') at rows 30–39
  - 10 date inversions where followup_date <= ct_date at rows 40–49
  - 5 out-of-range BMI values (< 10 or > 70) at rows 50–54
  - 5 out-of-range fev1 values (< 10 or > 200) at rows 55–59
"""
from __future__ import annotations

import logging
from pathlib import Path

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

# ── Constants ────────────────────────────────────────────────────────────────

N_PATIENTS = 1000
RANDOM_SEED = 42

_SEX_CATEGORIES = ["Male", "Female", "Other"]
_SMOKING_CATEGORIES = ["Never", "Former", "Current"]
_CVD_CATEGORIES = ["Yes", "No"]

# Defect slice indices (deterministic, document for test assertions)
DUPLICATE_ID_ROWS = list(range(10, 15))   # copy IDs from rows 0–4
MISSING_VAL_ROWS = list(range(100, 130))  # will have NaN injected
INVALID_AGE_ROWS = list(range(20, 28))    # age set outside [0, 120]
INVALID_SEX_ROWS = list(range(30, 40))    # sex set to "Unknown"
DATE_INVERSION_ROWS = list(range(40, 50)) # followup <= ct_date
INVALID_BMI_ROWS = list(range(50, 55))    # BMI outside [10, 70]
INVALID_FEV1_ROWS = list(range(55, 60))   # fev1 outside [10, 200]


# ── Generation helpers ────────────────────────────────────────────────────────

def _make_dates(
    rng: np.random.Generator,
    n: int,
    start: str = "2018-01-01",
    end: str = "2023-12-31",
) -> tuple[pd.Series, pd.Series]:
    """Generate (ct_date, followup_date) pairs, followup > ct by 30–730 days."""
    origin = pd.Timestamp(start)
    range_days = (pd.Timestamp(end) - origin).days

    ct_offsets = rng.integers(0, range_days, size=n)
    ct_dates = pd.to_datetime([origin + pd.Timedelta(days=int(d)) for d in ct_offsets])

    followup_offsets = rng.integers(30, 730, size=n)
    followup_dates = ct_dates + pd.to_timedelta(followup_offsets, unit="D")

    return (
        pd.Series(ct_dates.strftime("%Y-%m-%d"), name="ct_date"),
        pd.Series(followup_dates.strftime("%Y-%m-%d"), name="followup_date"),
    )


# ── Public API ────────────────────────────────────────────────────────────────

def generate_dataset(n: int = N_PATIENTS, seed: int = RANDOM_SEED) -> pd.DataFrame:
    """
    Generate a reproducible synthetic clinical dataset with injected defects.

    Parameters
    ----------
    n : int
        Number of patient rows (default 1000).
    seed : int
        Random seed for full reproducibility (default 42).

    Returns
    -------
    pd.DataFrame
        Dataset with canonical column names.
    """
    rng = np.random.default_rng(seed)

    # ── Base clean data ──────────────────────────────────────────────────────
    patient_ids = [f"PAT{str(i).zfill(5)}" for i in range(n)]

    age = rng.integers(18, 85, size=n).astype(float)
    sex = rng.choice(_SEX_CATEGORIES, size=n, p=[0.49, 0.49, 0.02])
    bmi = rng.uniform(17.0, 45.0, size=n).round(1)
    smoking_status = rng.choice(_SMOKING_CATEGORIES, size=n, p=[0.40, 0.35, 0.25])

    # pack_years: 0 for Never smokers, else random
    pack_years = np.where(
        smoking_status == "Never",
        0.0,
        rng.uniform(0.5, 80.0, size=n).round(1),
    )

    fev1 = rng.uniform(40.0, 130.0, size=n).round(1)
    baseline_cvd = rng.choice(_CVD_CATEGORIES, size=n, p=[0.25, 0.75])

    ct_dates, followup_dates = _make_dates(rng, n)

    df = pd.DataFrame(
        {
            "patient_id": patient_ids,
            "age": age,
            "sex": sex,
            "bmi": bmi,
            "smoking_status": smoking_status,
            "pack_years": pack_years,
            "fev1_percent_predicted": fev1,
            "baseline_cvd": baseline_cvd,
            "ct_date": ct_dates,
            "followup_date": followup_dates,
        }
    )

    # ── Inject defects ───────────────────────────────────────────────────────

    # 1. Duplicate patient IDs: copy IDs from first 5 rows
    for i, dup_row in enumerate(DUPLICATE_ID_ROWS):
        df.at[dup_row, "patient_id"] = df.at[i, "patient_id"]

    # 2. Missing values: NaN in several required columns
    missing_cols = ["age", "bmi", "fev1_percent_predicted"]
    for idx, col in zip(MISSING_VAL_ROWS, missing_cols * (len(MISSING_VAL_ROWS) // len(missing_cols) + 1)):
        df.at[idx, col] = np.nan

    # 3. Out-of-range ages (negative or > 120)
    bad_ages = [-5, 999, -1, 130, -10, 125, 200, -3]
    for row, bad_age in zip(INVALID_AGE_ROWS, bad_ages):
        df.at[row, "age"] = float(bad_age)

    # 4. Invalid sex categories
    for row in INVALID_SEX_ROWS:
        df.at[row, "sex"] = "Unknown"

    # 5. Date inversions: set followup_date to before ct_date
    for row in DATE_INVERSION_ROWS:
        ct = pd.Timestamp(df.at[row, "ct_date"])
        df.at[row, "followup_date"] = (ct - pd.Timedelta(days=rng.integers(1, 30).item())).strftime("%Y-%m-%d")

    # 6. Out-of-range BMI values
    bad_bmis = [5.0, 80.0, 3.5, 90.0, 7.0]
    for row, bad_bmi in zip(INVALID_BMI_ROWS, bad_bmis):
        df.at[row, "bmi"] = bad_bmi

    # 7. Out-of-range FEV1 values
    bad_fev1s = [5.0, 210.0, 3.0, 250.0, 8.0]
    for row, bad_fev1 in zip(INVALID_FEV1_ROWS, bad_fev1s):
        df.at[row, "fev1_percent_predicted"] = bad_fev1

    logger.info(
        "Generated dataset: %d rows, %d injected defect rows",
        n,
        len(
            DUPLICATE_ID_ROWS
            + MISSING_VAL_ROWS
            + INVALID_AGE_ROWS
            + INVALID_SEX_ROWS
            + DATE_INVERSION_ROWS
            + INVALID_BMI_ROWS
            + INVALID_FEV1_ROWS
        ),
    )
    return df


def save_dataset(df: pd.DataFrame, path: str | Path) -> None:
    """
    Save a DataFrame to CSV.

    Parameters
    ----------
    df : pd.DataFrame
        Dataset to save.
    path : str or Path
        Destination file path.
    """
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(out, index=False)
    logger.info("Dataset saved to %s", out)
