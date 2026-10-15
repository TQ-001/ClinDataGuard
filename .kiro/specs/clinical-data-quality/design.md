# ClinDataGuard – Design

## Architecture Overview

```
app.py  (Streamlit UI)
   │
   ├── src/generator.py   – Synthetic dataset generation
   ├── src/schema.py      – Schema loading & alias resolution
   ├── src/validator.py   – Validation logic
   └── src/reporting.py   – Issue export (CSV / JSON)

config/schema.yaml         – Field definitions
tests/test_validator.py    – pytest test suite
```

### Data Flow
```
CSV Upload / Generate
        │
        ▼
  schema.load_schema()        ← config/schema.yaml
        │
        ▼
  schema.resolve_aliases()    (rename columns; raise on collision)
        │
        ▼
  validator.validate()        (returns List[Issue])
        │
        ▼
  reporting.issues_to_csv()   /   reporting.summary_to_json()
        │
        ▼
  Streamlit UI display + download buttons
```

---

## Module Designs

### config/schema.yaml
```yaml
fields:
  patient_id:
    type: string
    required: true
    aliases: [id, pat_id, subject_id]
  age:
    type: integer
    required: true
    range: {min: 0, max: 120}
    aliases: [age_years]
  ...
```

### src/schema.py – `SchemaLoader`
- `load(path) -> dict`: parse YAML, return field map.
- `resolve_aliases(df, schema) -> DataFrame`: rename columns to canonical names; raise `AliasCollisionError` if two input columns map to the same canonical name.
- `AliasCollisionError(Exception)`: carries colliding column names.

### src/generator.py – `generate_dataset`
- `generate_dataset(n=1000, seed=42) -> pd.DataFrame`: returns a DataFrame with injected defects.
- `save_dataset(df, path)`: write to CSV.
- Defect categories injected: missing values (~3%), out-of-range ages, duplicate IDs (5), invalid sex categories, date inversions (10), invalid BMI values.

### src/validator.py – `validate`
```python
@dataclass
class Issue:
    row_number: int
    patient_id: str | None
    column: str
    rule_id: str
    severity: str   # "error" | "warning"
    observed_value: str
    explanation: str

def validate(df: pd.DataFrame, schema: dict) -> list[Issue]:
    ...
```
Rule execution order:
1. RULE-MISSING-COL (dataset level, returns early if critical columns missing)
2. RULE-DUPLICATE-ID
3. Per-row/per-column: RULE-MISSING-VAL, RULE-TYPE-ERROR, RULE-RANGE, RULE-CATEGORY
4. RULE-DATE-ORDER

### src/reporting.py
- `issues_to_dataframe(issues) -> pd.DataFrame`
- `issues_to_csv(issues, path) -> str`  (returns CSV string if path is None)
- `summary_to_json(df, issues) -> str`  (returns JSON string)

### app.py
Streamlit layout:
- Sidebar: Generate Sample Data button → downloads `sample_data.csv`
- Main: File uploader → triggers validation pipeline → shows summary metrics + filterable issues table + download buttons.
- Error handling: catches `AliasCollisionError`, encoding errors, empty file, zero issues.

---

## Data Model

| Field | Type | Required | Range / Categories |
|---|---|---|---|
| patient_id | string | yes | unique |
| age | integer | yes | 0–120 |
| sex | string | yes | Male, Female, Other |
| bmi | float | yes | 10.0–70.0 |
| smoking_status | string | yes | Never, Former, Current |
| pack_years | float | no | 0–300 |
| fev1_percent_predicted | float | yes | 10–200 |
| baseline_cvd | string | yes | Yes, No |
| ct_date | date | yes | ISO 8601 |
| followup_date | date | yes | ISO 8601; must be > ct_date |

---

## Error Handling Strategy
- Schema load errors → logged + raised immediately.
- Alias collision → `AliasCollisionError` propagated to UI.
- Encoding errors on upload → caught, user-friendly message shown.
- Empty DataFrame → validator returns empty issue list, summary shows zero issues.
- Date parse errors → treated as RULE-TYPE-ERROR issues, not crashes.
