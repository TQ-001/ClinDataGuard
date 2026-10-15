# ClinDataGuard – Implementation Tasks

## Task Order (incremental, each builds on the last)

### Task 1 – Schema Config  
File: `config/schema.yaml`  
Define all 10 fields with canonical names, aliases, types, required flags, ranges, and categories.  
Acceptance: File loads with PyYAML without errors.

### Task 2 – Schema Module  
File: `src/schema.py`  
Implement `load()`, `resolve_aliases()`, and `AliasCollisionError`.  
Acceptance: Alias mapping works; collision raises explicit error.

### Task 3 – Generator  
File: `src/generator.py`  
Implement `generate_dataset(n=1000, seed=42)` with injected defects and `save_dataset()`.  
Acceptance: Two runs with same seed produce identical CSV; defects are present.

### Task 4 – Validator  
File: `src/validator.py`  
Implement `Issue` dataclass and `validate(df, schema) -> list[Issue]`.  
Detect all 7 rule types.  
Acceptance: Returns structured issues; never modifies df.

### Task 5 – Reporting  
File: `src/reporting.py`  
Implement `issues_to_csv()`, `issues_to_dataframe()`, `summary_to_json()`.  
Acceptance: Output is valid CSV and JSON; round-trips correctly.

### Task 6 – Streamlit UI  
File: `app.py`  
Wire all modules into the Streamlit interface.  
Acceptance: `streamlit run app.py` launches; all interactions work; edge cases handled.

### Task 7 – Tests  
File: `tests/test_validator.py`  
Write 8+ pytest tests.  
Acceptance: `pytest -q` passes with no failures.

### Task 8 – Packaging  
Files: `requirements.txt`, `README.md`  
Pin dependency versions; document setup, architecture, test commands, limitations.  
Acceptance: `pip install -r requirements.txt` succeeds; README is complete.
