
Build a portfolio-quality MVP called ClinDataGuard using spec-driven development.

OBJECTIVE
Create a local, deterministic, schema-aware clinical data quality auditing application. The project must be fully implementable in a 90-minute coding session and showcase software engineering, automated testing, and reproducible clinical data validation.

TECH STACK
Python 3.11+, pandas, Pydantic, PyYAML, Streamlit, pytest. Use standard library for JSON and logging. No database, Docker, cloud infrastructure, LLM API, authentication, or external datasets.

WORKFLOW
Use Kiro Quick Spec to generate requirements.md, design.md, and tasks.md under .kiro/specs/clinical-data-quality/. Make all requirements verifiable, preferably EARS-style. Group implementation into at most six independent, incremental tasks. Prioritize an executable MVP, not extensive documentation. Do not start implementing before the spec artifacts have been generated.

FUNCTIONAL REQUIREMENTS
1. Generate a reproducible synthetic CSV with 1000 fictional patients using a fixed random seed; include intentionally injected and labelled-in-test data quality defects.
2. Define a YAML schema with canonical column names, supported aliases, data types, required fields, allowed categories and numeric ranges.
3. Support these fields: patient_id, age, sex, bmi, smoking_status, pack_years, fev1_percent_predicted, baseline_cvd, ct_date, followup_date.
4. Provide a pure-Python validator callable without the UI.
5. Detect: missing required columns, missing cell values, type errors, out-of-range values, duplicate patient IDs, invalid categories, and followup_date earlier than ct_date.
6. Normalize column name aliases before validation; report collisions/ambiguity explicitly instead of silently overwriting.
7. For invalid values, return issues with: row_number, patient_id (when available), column, rule_id, severity, observed_value, and explanation.
8. Never overwrite or auto-correct source records.
9. Provide a Streamlit interface with Generate Sample Data, CSV uploader, validation summary, issues table with filters, and downloads for issues CSV and JSON summary.
10. Handle empty files, invalid encodings, absent columns, missing values, invalid dates and datasets with zero issues.
11. Include at least 8 pytest tests covering positive, negative and edge cases.
12. Include a README with setup, architecture, test commands and limitations.

ACCEPTANCE CRITERIA
- streamlit run app.py launches the UI.
- pytest -q passes.
- Fixed-seed sample generation is reproducible.
- Duplicate IDs and invalid dates are flagged correctly.
- FEV1 aliases are recognized.
- Alias collisions generate explicit errors.
- Reports are valid CSV and JSON.
- Processing is entirely local.

ARCHITECTURE
app.py
src/generator.py
src/schema.py
src/validator.py
src/reporting.py
config/schema.yaml
tests/test_validator.py
requirements.txt
README.md

Use: DataFrame -> alias resolution -> validation -> issues -> summary -> UI and exports.

CONSTRAINTS
Strict 90-minute budget. No cloud, Docker, authentication, database, external datasets or LLM APIs. Keep code modular, deterministic and testable. Ask no questions unless blocked. Defer optional features.

After generating specs, show the ordered implementation tasks.
  