"""
app.py
ClinDataGuard – Streamlit UI

Launch with:
    streamlit run app.py
"""
from __future__ import annotations

import io
import logging
import sys
from pathlib import Path

import pandas as pd
import streamlit as st

# Ensure the project root is on the path so src.* imports work
sys.path.insert(0, str(Path(__file__).parent))

from src import schema as schema_mod
from src.generator import generate_dataset
from src.reporting import issues_to_csv, issues_to_dataframe, summary_to_json
from src.schema import AliasCollisionError
from src.validator import validate

logging.basicConfig(level=logging.INFO)

# ── Page config ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="ClinDataGuard",
    page_icon="🩺",
    layout="wide",
)

SCHEMA_PATH = Path(__file__).parent / "config" / "schema.yaml"


@st.cache_resource
def _load_schema() -> dict:
    """Load schema once and cache."""
    return schema_mod.load(SCHEMA_PATH)


def _run_validation(df_raw: pd.DataFrame, schema: dict):
    """
    Run alias resolution + validation pipeline.
    Returns (df_resolved, issues, error_message).
    """
    try:
        df_resolved = schema_mod.resolve_aliases(df_raw, schema)
    except AliasCollisionError as exc:
        return None, [], str(exc)
    except Exception as exc:
        return None, [], f"Alias resolution error: {exc}"

    issues = validate(df_resolved, schema)
    return df_resolved, issues, None


def _severity_badge(severity: str) -> str:
    colour = {"error": "🔴", "warning": "🟡"}.get(severity, "⚪")
    return f"{colour} {severity.title()}"


# ── Header ────────────────────────────────────────────────────────────────────
st.title("🩺 ClinDataGuard")
st.caption("Local, deterministic clinical data quality auditing")

# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.header("⚙️ Tools")

    st.subheader("Generate Sample Data")
    st.write(
        "Produce a reproducible 1000-patient CSV (seed=42) with "
        "intentionally injected defects to explore the validator."
    )
    if st.button("🔄 Generate & Download Sample CSV", use_container_width=True):
        with st.spinner("Generating…"):
            sample_df = generate_dataset()
        csv_bytes = sample_df.to_csv(index=False).encode("utf-8")
        st.download_button(
            label="⬇️ Download sample_data.csv",
            data=csv_bytes,
            file_name="sample_data.csv",
            mime="text/csv",
            use_container_width=True,
        )
        st.success(f"Generated {len(sample_df):,} rows.")

    st.divider()
    st.caption("v1.0.0 · All processing is local")

# ── Main area ─────────────────────────────────────────────────────────────────
schema = _load_schema()

uploaded_file = st.file_uploader(
    "📂 Upload a clinical CSV for validation",
    type=["csv"],
    help="Upload any CSV with clinical patient data. "
         "Column names may use aliases defined in config/schema.yaml.",
)

if uploaded_file is None:
    st.info(
        "Upload a CSV file above to begin validation, or generate a sample "
        "dataset from the sidebar."
    )
    st.stop()

# ── Load uploaded file ────────────────────────────────────────────────────────
try:
    raw_bytes = uploaded_file.read()
    if len(raw_bytes) == 0:
        st.error("The uploaded file is empty. Please upload a non-empty CSV.")
        st.stop()

    try:
        df_raw = pd.read_csv(io.BytesIO(raw_bytes), encoding="utf-8")
    except UnicodeDecodeError:
        try:
            df_raw = pd.read_csv(io.BytesIO(raw_bytes), encoding="latin-1")
            st.warning("File decoded with latin-1 encoding (not UTF-8).")
        except Exception as enc_err:
            st.error(f"Cannot decode file: {enc_err}")
            st.stop()

except Exception as exc:
    st.error(f"Failed to read file: {exc}")
    st.stop()

if df_raw.empty:
    st.warning("The uploaded file has no data rows.")
    st.stop()

st.write(f"**Loaded:** {len(df_raw):,} rows × {len(df_raw.columns)} columns")

# ── Run validation ────────────────────────────────────────────────────────────
with st.spinner("Validating…"):
    df_resolved, issues, error_msg = _run_validation(df_raw, schema)

if error_msg:
    st.error(f"**Validation error:** {error_msg}")
    st.stop()

# ── Summary metrics ───────────────────────────────────────────────────────────
st.subheader("📊 Validation Summary")

total_errors = sum(1 for i in issues if i.severity == "error")
total_warnings = sum(1 for i in issues if i.severity == "warning")

col1, col2, col3, col4 = st.columns(4)
col1.metric("Total Rows", f"{len(df_raw):,}")
col2.metric("Total Issues", f"{len(issues):,}")
col3.metric("🔴 Errors", f"{total_errors:,}")
col4.metric("🟡 Warnings", f"{total_warnings:,}")

if not issues:
    st.success("✅ No data quality issues found — dataset is clean!")
else:
    # ── Issues by rule breakdown ──────────────────────────────────────────────
    with st.expander("Issues by Rule", expanded=False):
        rule_counts: dict[str, int] = {}
        for iss in issues:
            rule_counts[iss.rule_id] = rule_counts.get(iss.rule_id, 0) + 1
        rule_df = pd.DataFrame(
            [(rule, count) for rule, count in sorted(rule_counts.items())],
            columns=["Rule", "Count"],
        )
        st.dataframe(rule_df, use_container_width=True, hide_index=True)

    # ── Issues table with filters ─────────────────────────────────────────────
    st.subheader("🔍 Issues Table")

    issues_df = issues_to_dataframe(issues)

    # Filter controls
    filter_col1, filter_col2, filter_col3 = st.columns(3)

    with filter_col1:
        all_severities = sorted(issues_df["severity"].unique().tolist())
        selected_severities = st.multiselect(
            "Severity",
            options=all_severities,
            default=all_severities,
        )

    with filter_col2:
        all_rules = sorted(issues_df["rule_id"].unique().tolist())
        selected_rules = st.multiselect(
            "Rule",
            options=all_rules,
            default=all_rules,
        )

    with filter_col3:
        all_cols = sorted(issues_df["column"].unique().tolist())
        selected_cols = st.multiselect(
            "Column",
            options=all_cols,
            default=all_cols,
        )

    filtered_df = issues_df[
        issues_df["severity"].isin(selected_severities)
        & issues_df["rule_id"].isin(selected_rules)
        & issues_df["column"].isin(selected_cols)
    ]

    st.write(f"Showing **{len(filtered_df):,}** of **{len(issues_df):,}** issues")
    st.dataframe(filtered_df, use_container_width=True, hide_index=True)

# ── Downloads ─────────────────────────────────────────────────────────────────
st.subheader("⬇️ Export Results")

dl_col1, dl_col2 = st.columns(2)

with dl_col1:
    csv_content = issues_to_csv(issues)
    st.download_button(
        label="📄 Download Issues CSV",
        data=csv_content.encode("utf-8"),
        file_name="clindataguard_issues.csv",
        mime="text/csv",
        use_container_width=True,
        disabled=(len(issues) == 0),
    )

with dl_col2:
    json_content = summary_to_json(df_resolved if df_resolved is not None else df_raw, issues)
    st.download_button(
        label="📋 Download Summary JSON",
        data=json_content.encode("utf-8"),
        file_name="clindataguard_summary.json",
        mime="application/json",
        use_container_width=True,
    )
