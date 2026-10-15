"""
src/schema.py
Schema loading and alias resolution for ClinDataGuard.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import pandas as pd
import yaml

logger = logging.getLogger(__name__)

# Default schema path relative to project root
DEFAULT_SCHEMA_PATH = Path(__file__).parent.parent / "config" / "schema.yaml"


class AliasCollisionError(Exception):
    """Raised when two or more input columns resolve to the same canonical name."""

    def __init__(self, canonical: str, colliding_columns: list[str]) -> None:
        self.canonical = canonical
        self.colliding_columns = colliding_columns
        super().__init__(
            f"Alias collision: multiple input columns {colliding_columns!r} "
            f"all map to canonical name '{canonical}'."
        )


def load(path: str | Path | None = None) -> dict[str, Any]:
    """
    Load and return the field schema from a YAML file.

    Parameters
    ----------
    path : str or Path, optional
        Path to the schema YAML file. Defaults to config/schema.yaml.

    Returns
    -------
    dict
        Parsed schema dict with top-level key ``fields``.

    Raises
    ------
    FileNotFoundError
        If the schema file does not exist.
    yaml.YAMLError
        If the file cannot be parsed.
    """
    schema_path = Path(path) if path else DEFAULT_SCHEMA_PATH
    if not schema_path.exists():
        raise FileNotFoundError(f"Schema file not found: {schema_path}")

    with schema_path.open("r", encoding="utf-8") as fh:
        schema = yaml.safe_load(fh)

    if not isinstance(schema, dict) or "fields" not in schema:
        raise ValueError(f"Schema at {schema_path} must contain a top-level 'fields' key.")

    logger.debug("Schema loaded from %s (%d fields)", schema_path, len(schema["fields"]))
    return schema


def build_alias_map(schema: dict[str, Any]) -> dict[str, str]:
    """
    Build a mapping from every alias (and the canonical name itself) to the canonical name.

    Parameters
    ----------
    schema : dict
        Parsed schema (result of ``load()``).

    Returns
    -------
    dict[str, str]
        ``{alias_or_canonical: canonical_name}``
    """
    alias_map: dict[str, str] = {}
    for canonical, field_def in schema["fields"].items():
        # The canonical name maps to itself
        alias_map[canonical] = canonical
        for alias in field_def.get("aliases", []):
            alias_map[alias] = canonical
    return alias_map


def resolve_aliases(
    df: pd.DataFrame,
    schema: dict[str, Any],
) -> pd.DataFrame:
    """
    Rename DataFrame columns from aliases to their canonical names.

    Rules:
    - Columns already using a canonical name are kept as-is.
    - Columns matching a known alias are renamed to the canonical name.
    - Columns not in the alias map are left unchanged (they will fail
      RULE-MISSING-COL validation if required).
    - If two or more input columns resolve to the **same** canonical name,
      an ``AliasCollisionError`` is raised immediately.

    Parameters
    ----------
    df : pd.DataFrame
        Input DataFrame (never modified in-place; a renamed copy is returned).
    schema : dict
        Parsed schema (result of ``load()``).

    Returns
    -------
    pd.DataFrame
        New DataFrame with canonical column names.

    Raises
    ------
    AliasCollisionError
        If two input columns map to the same canonical field.
    """
    alias_map = build_alias_map(schema)

    # Determine which canonical name each existing column resolves to
    resolved: dict[str, str] = {}  # input_col -> canonical
    canonical_sources: dict[str, list[str]] = {}  # canonical -> [input_cols]

    for col in df.columns:
        canonical = alias_map.get(col, col)  # unknown cols keep their name
        resolved[col] = canonical
        canonical_sources.setdefault(canonical, []).append(col)

    # Check for collisions
    for canonical, sources in canonical_sources.items():
        if len(sources) > 1 and canonical in schema["fields"]:
            raise AliasCollisionError(canonical, sources)

    # Build the rename map (only columns that actually change)
    rename_map = {col: can for col, can in resolved.items() if col != can}

    if rename_map:
        logger.debug("Renaming columns: %s", rename_map)

    return df.rename(columns=rename_map)
