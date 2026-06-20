"""
Schema validation utilities.

Validates pipeline objects against the canonical sub-schemas defined in
configs/schema.json.  Each public function returns a list of validation
error strings (empty = valid).  They never raise, so they are safe to
call from any pipeline module without disrupting the run.

Usage::

    from src.utils.schema_utils import validate_id_dict, validate_figure_extraction

    errs = validate_id_dict(id_dict)
    if errs:
        for e in errs:
            logger.warning(f"[schema] id_dict: {e}")

Requires ``jsonschema`` (already in requirements via openpyxl chain; if
missing, validation is silently skipped and an empty list is returned).
"""

import json
from pathlib import Path
from typing import Any, List

from src.utils.logging_utils import get_logger

logger = get_logger(__name__)

_SCHEMA_PATH = Path(__file__).parents[2] / "configs" / "schema.json"
_schema_cache: dict = {}


def _load_schema() -> dict:
    global _schema_cache
    if _schema_cache:
        return _schema_cache
    try:
        _schema_cache = json.loads(_SCHEMA_PATH.read_text(encoding="utf-8"))
    except Exception as exc:
        logger.warning(f"[schema_utils] Could not load schema.json: {exc}")
        _schema_cache = {}
    return _schema_cache


def _validate(obj: Any, definition_name: str) -> List[str]:
    """
    Validate *obj* against definitions.<definition_name> in schema.json.
    Returns a list of error message strings (empty list = valid).
    """
    try:
        import jsonschema
    except ImportError:
        return []   # jsonschema not installed — skip silently

    schema = _load_schema()
    if not schema:
        return []

    sub_schema = schema.get("definitions", {}).get(definition_name)
    if not sub_schema:
        return [f"definition '{definition_name}' not found in schema.json"]

    # Resolve $ref within the same document
    resolver = jsonschema.RefResolver.from_schema(schema)

    errors = []
    try:
        validator = jsonschema.Draft7Validator(sub_schema, resolver=resolver)
        for err in validator.iter_errors(obj):
            errors.append(f"{' -> '.join(str(p) for p in err.absolute_path) or '(root)'}: {err.message}")
    except Exception as exc:
        errors.append(f"validator error: {exc}")
    return errors


# ── Public validators ─────────────────────────────────────────────────────────

def validate_id_dict(obj: Any) -> List[str]:
    """Validate Module 2.02 output against the 'id_dict' schema."""
    return _validate(obj, "id_dict")


def validate_figure_extraction(obj: Any) -> List[str]:
    """Validate one Module 3 extraction result against 'figure_extraction'."""
    return _validate(obj, "figure_extraction")


def validate_si_data(obj: Any) -> List[str]:
    """Validate Module 2.04 output against the 'si_data' schema."""
    return _validate(obj, "si_data")


def validate_merged_scheme(obj: Any) -> List[str]:
    """Validate one post-processed scheme against the 'merged_scheme' schema."""
    return _validate(obj, "merged_scheme")


def validate_export_row(obj: Any) -> List[str]:
    """Validate one CSV/Excel export row against 'export_row_solution'."""
    return _validate(obj, "export_row_solution")


def log_validation(obj: Any, definition_name: str, context: str = "") -> bool:
    """
    Convenience wrapper: validate and log any errors as warnings.

    Returns True if valid, False if errors were found.
    """
    errs = _validate(obj, definition_name)
    if errs:
        prefix = f"[schema:{context}] " if context else "[schema] "
        for e in errs:
            logger.warning(f"{prefix}{e}")
        return False
    return True
