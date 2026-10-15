# ClinDataGuard

> A local, deterministic, schema-aware clinical data quality auditing tool.

Clinical research datasets arrive from multiple sites, instruments, and analysts.
Column names differ (`fev1_pp`, `fev1%pred`, `percent_predicted_fev1`), required
fields go missing, dates get transposed, and numeric values fall outside
physiologically plausible ranges — all silently, before any analysis runs.

**ClinDataGuard** validates CSV patient data against a declarative YAML schema,
reports every anomaly as a structured issue with row, column, rule, and
explanation, and presents results through a Streamlit UI with filterable tables
and one-click exports. All processing is local and stateless; no data leaves the
machine.

---

## Contents

- [Problem and solution](#problem-and-solution)
- [Architecture](#architecture)
- [Technologies](#technologies)
- [Schema and validation rules](#schema-and-validation-rules)
- [Setup](#setup)
- [Running the app](#running-the-app)
- [Running tests](#running-tests)
- [Example results](#example-results)
- [Kiro spec-driven development workflow](#kiro-spec-driven-development-workflow)
- [Limitations](#limitations)

---

## Problem and solution

### The problem

Multi-site clinical studies routinely produce CSVs that contain:

- **Column name drift** — the same field has different names across sites or
  instruments (`age`, `age_years`, `age_yr`).
- **Missing required values** — a required `fev1_percent_predicted` cell is blank.
- **Type errors** — a BMI column contains the string `"not measured"`.
- **Out-of-range values** — an age of `999` or a BMI of `3.5`.
- **Invalid categories** — `sex` contains `"Unknown"` instead of
  `Male / Female / Other`.
- **Duplicate identifiers** — the same `patient_id` appears on two rows.
- **Date inversions** — `followup_date` is earlier than `ct_date`.

These defects are invisible to downstream statistical pipelines until they
produce wrong results or crash.

### The solution

ClinDataGuard sits at the **ingestion gate**, before any analysis:

1. The schema owner defines field types, required flags, allowed ranges,
   categories, and column aliases in one YAML file.
2. Any incoming CSV is normalised through alias resolution, then validated
   against every rule.
3. Every violation is returned as a structured `Issue` — row number, patient ID,
   column, rule ID, observed value, explanation — with no modification to the
   source data.
4. The Streamlit UI lets analysts browse, filter, and export issues before
   deciding whether to correct the upstream source.

---

## Architecture

```
clindataguard/
├── app.py                     # Streamlit UI entry point
├── config/
│   └── schema.yaml            # Field definitions (types, ranges, aliases, categories)
├── src/
│   ├── schema.py              # YAML loader + alias resolution + AliasCollisionError
│   ├── generator.py           # Reproducible 1 000-row synthetic dataset with injected defects
│   ├── validator.py           # Pure-Python validation engine → List[Issue]
│   └── reporting.py           # CSV and JSON export helpers
├── tests/
│   └── test_validator.py      # pytest suite (23 tests)
├── .kiro/specs/clinical-data-quality/
│   ├── requirements.md        # EARS-style functional requirements
│   ├── design.md              # Module design and data flow
│   └── tasks.md               # Ordered implementation tasks
├── requirements.txt
└── README.md
```

### Data flow

```
CSV Upload  ──or──  Generate Sample (seed=42)
        │
        ▼
  schema.load()                 ← config/schema.yaml
        │
        ▼
  schema.resolve_aliases()      rename variant column names to canonical names
        │                       raise AliasCollisionError if two columns
        │                       resolve to the same canonical name
        ▼
  validator.validate()          returns List[Issue]
        │                       never modifies source data
        ▼
  reporting.issues_to_csv()     seven-column CSV
  reporting.summary_to_json()   total_rows / total_issues / by_severity / by_rule
        │
        ▼
  Streamlit UI                  summary metrics · filterable table · download buttons
```

### Module responsibilities

| Module | Responsibility |
|--------|---------------|
| `src/schema.py` | Load `schema.yaml`; build alias map; rename columns; raise on collision |
| `src/generator.py` | Produce deterministic 1 000-row CSV with documented injected defects |
| `src/validator.py` | Apply all seven rules; return `List[Issue]`; never mutate input |
| `src/reporting.py` | Serialise issues to CSV string / file; produce JSON summary |
| `app.py` | Wire modules into Streamlit; handle edge cases; offer downloads |

The validator has **no Streamlit dependency** and can be used as a library:

```python
from src.schema import load, resolve_aliases
from src.validator import validate

schema = load()                          # reads config/schema.yaml
df     = pd.read_csv("patients.csv")
df     = resolve_aliases(df, schema)
issues = validate(df, schema)            # List[Issue], source df unchanged

for issue in issues:
    print(issue.rule_id, issue.row_number, issue.explanation)
```

---

## Technologies

| Technology | Version | Role |
|------------|---------|------|
| Python | 3.9 + | Runtime |
| pandas | 2.2.3 | DataFrame I/O, type coercion, date parsing |
| PyYAML | 6.0.2 | Schema definition loading |
| Streamlit | 1.41.1 | Browser UI |
| pytest | 8.3.5 | Automated test suite |
| NumPy | 2.0.2 | Random number generation for synthetic data |
| Pydantic | 2.10.6 | Available; data model validation |

No database, Docker, cloud service, authentication layer, or external API is
used. All data stays on the local machine.

---

## Schema and validation rules

The schema lives in `config/schema.yaml`. Adding a new field, alias, or
category requires only a YAML edit — no code change.

### Fields

| Field | Type | Required | Constraint |
|-------|------|----------|-----------|
| `patient_id` | string | ✓ | unique across dataset |
| `age` | integer | ✓ | 0 – 120 |
| `sex` | string | ✓ | Male, Female, Other |
| `bmi` | float | ✓ | 10.0 – 70.0 |
| `smoking_status` | string | ✓ | Never, Former, Current |
| `pack_years` | float | | 0 – 300 |
| `fev1_percent_predicted` | float | ✓ | 10.0 – 200.0 |
| `baseline_cvd` | string | ✓ | Yes, No |
| `ct_date` | date | ✓ | ISO 8601 |
| `followup_date` | date | ✓ | ISO 8601; must be strictly after `ct_date` |

### Recognised FEV1 aliases

Any of these column names in an uploaded CSV is automatically renamed to
`fev1_percent_predicted` before validation:

```
fev1_pp  fev1pp  fev1%pred  fev1_pct_pred  fev1_percent
fev1_pct  fev1_%predicted  percent_predicted_fev1  fev1_predicted_pct
```

### Validation rules

| Rule ID | Trigger | Severity |
|---------|---------|---------|
| `RULE-MISSING-COL` | Required column absent from dataset | error |
| `RULE-MISSING-VAL` | Required cell is null or empty | error |
| `RULE-TYPE-ERROR` | Value cannot be cast to declared type | error |
| `RULE-RANGE` | Numeric value outside min / max | error |
| `RULE-CATEGORY` | Categorical value not in allowed set | error |
| `RULE-DUPLICATE-ID` | `patient_id` appears more than once | error |
| `RULE-DATE-ORDER` | `followup_date` ≤ `ct_date` | error |

Every issue record contains:

```
row_number    patient_id    column    rule_id    severity    observed_value    explanation
```

---

## Setup

```bash
# Python 3.9 or later required
python3 -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate

pip install -r requirements.txt
```

---

## Running the app

```bash
streamlit run app.py
```

Opens at `http://localhost:8501`.

**Workflow:**

1. **Sidebar → Generate & Download Sample CSV** — produces a reproducible
   1 000-row file (seed = 42) with labelled defects.
2. **Upload CSV** — accepts any clinical CSV; column aliases are resolved
   automatically.
3. **Review summary** — total rows, total issues, errors, warnings.
4. **Filter issues table** — narrow by severity, rule, or column.
5. **Download** — export issues as CSV or the summary as JSON.

The app handles: empty files, non-UTF-8 encodings (latin-1 fallback),
header-only CSVs, alias collisions, and datasets with zero issues.

---

## Running tests

```bash
# Short output
pytest -q

# Verbose with test names
pytest -v tests/test_validator.py
```

The test suite covers:

| Category | Tests |
|----------|-------|
| Valid data produces zero issues | 1 |
| Missing required column (`RULE-MISSING-COL`) | 1 |
| Duplicate patient IDs (`RULE-DUPLICATE-ID`) | 1 |
| Out-of-range values — age, BMI (`RULE-RANGE`) | 2 |
| Invalid categories — sex, smoking (`RULE-CATEGORY`) | 2 |
| Date order violations — before and equal (`RULE-DATE-ORDER`) | 2 |
| FEV1 and age alias resolution | 2 |
| Alias collision raises `AliasCollisionError` | 1 |
| Missing required cell (`RULE-MISSING-VAL`) | 1 |
| Type errors — non-numeric, unparseable date (`RULE-TYPE-ERROR`) | 2 |
| Empty DataFrame (no columns) returns zero issues | 1 |
| Header-only CSV flags missing required columns | 1 |
| Reproducibility — same seed, different seed | 2 |
| Seeded defects verified in generated sample | 4 |
| **Total** | **23** |

---

## Example results

The built-in synthetic dataset (`generate_dataset(seed=42)`) produces the
following validation summary. These numbers are deterministic — running the
generator twice with the same seed produces the same CSV and the same issues.

```json
{
  "total_rows": 1000,
  "total_issues": 73,
  "issues_by_severity": {
    "error": 73
  },
  "issues_by_rule": {
    "RULE-DUPLICATE-ID": 5,
    "RULE-MISSING-VAL": 30,
    "RULE-RANGE": 18,
    "RULE-CATEGORY": 10,
    "RULE-DATE-ORDER": 10
  }
}
```

Sample rows from the issues CSV export:

```
row_number,patient_id,column,rule_id,severity,observed_value,explanation
11,PAT00000,patient_id,RULE-DUPLICATE-ID,error,PAT00000,"Duplicate patient_id 'PAT00000' also appears at row 1."
21,PAT00020,age,RULE-RANGE,error,-5.0,"'age' value -5 is outside allowed range [0, 120]."
31,PAT00030,sex,RULE-CATEGORY,error,Unknown,"'sex' value 'Unknown' is not in allowed categories ['Male', 'Female', 'Other']."
41,PAT00040,followup_date,RULE-DATE-ORDER,error,2022-01-14,"followup_date (2022-01-14) must be after ct_date (2022-01-22)."
101,PAT00100,age,RULE-MISSING-VAL,error,<null>,"Required field 'age' is null/empty."
```

---

## Kiro spec-driven development workflow

This project was built using **Kiro**, an AI-assisted development tool that
separates specification from implementation.

### Workflow

```
1. ProjectInitPrompt.md          describe the project requirements in plain English
        │
        ▼
2. Kiro Quick Spec               generate three spec artifacts automatically:
        │                          requirements.md  (EARS-style functional requirements)
        │                          design.md        (module design, data flow, data model)
        │                          tasks.md         (ordered implementation tasks)
        ▼
3. Kiro implements tasks         each task maps to one or more source files;
        │                        implementation follows spec, not the other way around
        ▼
4. Kiro reviews against spec     every acceptance criterion in requirements.md
                                 is executed and verified before the session closes
```

### Spec artifacts

The full specification lives in `.kiro/specs/clinical-data-quality/`:

- **`requirements.md`** — EARS-style ("WHEN … the system SHALL …") functional
  and non-functional requirements, each traceable to a test.
- **`design.md`** — module responsibilities, data flow diagram, field data
  model, error-handling strategy.
- **`tasks.md`** — eight incremental tasks in dependency order, each with an
  acceptance criterion.

### Why this matters for a portfolio

Spec-driven development demonstrates that the design was deliberate:

- Requirements were written before any code.
- The architecture was reasoned through in `design.md` before modules were
  created.
- Every acceptance criterion has a corresponding test that was executed and
  passed, not assumed.

---

## Limitations

- **Performance** — validation is row-by-row Python; files larger than ~100 000
  rows will be slow. A vectorised rewrite using pandas masks would improve this.
- **Date ambiguity** — date parsing relies on `pandas.Timestamp`; formats like
  `01/02/03` may be misinterpreted depending on locale.
- **Cross-field consistency** — `pack_years > 0` for a `smoking_status = Never`
  patient is not flagged. This would require a cross-field rule, which is not
  currently in the schema.
- **Single-table only** — the validator operates on one flat CSV. Relational
  integrity across multiple tables is out of scope.
- **No correction** — the tool never modifies source data. Correcting issues is
  the responsibility of the upstream data owner.
- **No authentication** — the Streamlit UI is single-user and local. It is not
  suitable for a shared server without adding an authentication layer.
- **Stateless sessions** — validation results are not persisted; closing the
  browser tab discards them.
