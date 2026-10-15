# ClinDataGuard – Requirements

## Overview
ClinDataGuard is a local, deterministic, schema-aware clinical data quality auditing application. It validates CSV datasets containing patient respiratory/clinical data against a YAML-defined schema and produces structured audit reports.

---

## Functional Requirements

### FR-1: Synthetic Data Generation
- WHEN the user requests sample data, the system SHALL generate a reproducible CSV with exactly 1000 fictional patients using a fixed random seed (42).
- The generated dataset SHALL include intentionally injected data quality defects that are labelled in tests.
- Fixed-seed generation SHALL be deterministic: running twice produces identical output.

### FR-2: Schema Definition
- The system SHALL load field definitions from `config/schema.yaml`.
- The schema SHALL define for each field: canonical name, supported aliases, data type, required flag, allowed categories (for categorical fields), and numeric range (for numeric fields).
- Supported fields: `patient_id`, `age`, `sex`, `bmi`, `smoking_status`, `pack_years`, `fev1_percent_predicted`, `baseline_cvd`, `ct_date`, `followup_date`.

### FR-3: Alias Resolution
- WHEN a CSV is loaded, the system SHALL normalize column names using alias mappings defined in the schema before validation.
- WHEN two or more input columns resolve to the same canonical name, the system SHALL raise an explicit collision error instead of silently overwriting.
- FEV1 column aliases (e.g., `fev1_pp`, `fev1pp`, `fev1%pred`) SHALL be recognized and mapped to `fev1_percent_predicted`.

### FR-4: Validation Rules
The validator SHALL detect and report:
- **RULE-MISSING-COL**: Required columns absent from the dataset.
- **RULE-MISSING-VAL**: Null/empty cell values in required fields.
- **RULE-TYPE-ERROR**: Cell values that cannot be cast to the declared type.
- **RULE-RANGE**: Numeric values outside defined min/max bounds.
- **RULE-CATEGORY**: Categorical values not in the allowed set.
- **RULE-DUPLICATE-ID**: Duplicate `patient_id` values.
- **RULE-DATE-ORDER**: `followup_date` earlier than or equal to `ct_date`.

### FR-5: Issue Structure
- Each issue SHALL contain: `row_number`, `patient_id` (when available), `column`, `rule_id`, `severity`, `observed_value`, `explanation`.
- The validator SHALL never overwrite or auto-correct source records.

### FR-6: Reporting
- The system SHALL export issues to a CSV file.
- The system SHALL export a summary to a JSON file containing: total_rows, total_issues, issues_by_severity, issues_by_rule.

### FR-7: Streamlit UI
- The UI SHALL provide: Generate Sample Data button, CSV file uploader, validation summary panel, filterable issues table, download buttons for issues CSV and JSON summary.
- The UI SHALL handle: empty files, invalid encodings, absent columns, missing values, invalid dates, datasets with zero issues.

### FR-8: Testing
- The project SHALL include at least 8 pytest tests covering positive, negative, and edge cases.
- Tests SHALL verify: valid data passes, missing required column flagged, duplicate IDs flagged, out-of-range values flagged, invalid categories flagged, date order violations flagged, alias resolution works, alias collision raises error.

---

## Non-Functional Requirements

### NFR-1: Local Execution
All processing SHALL be entirely local; no network calls, cloud services, or external APIs.

### NFR-2: No Side Effects on Source Data
The system SHALL never modify input files or auto-correct source records.

### NFR-3: Determinism
All synthetic data generation SHALL be seeded and reproducible.

### NFR-4: Modularity
The validator SHALL be callable independently of the UI (pure Python, no Streamlit dependency).

### NFR-5: Technology
Python 3.11+, pandas, Pydantic, PyYAML, Streamlit, pytest. Standard library for JSON and logging. No database, Docker, or authentication.
