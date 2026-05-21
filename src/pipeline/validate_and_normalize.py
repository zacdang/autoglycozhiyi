"""
Step 10 — Validate and normalize the reaction record.

Checks
------
1. Required fields are present (not NR).
2. Values look chemically plausible (basic sanity checks).
3. Common abbreviations are expanded.

Adds
----
- completeness_score (fraction of tracked fields that are not NR)
- unresolved_fields  (list of fields still NR after all filling steps)

TODO: Add an LLM-based plausibility check using configs/prompts/validate_record.txt
      for deeper chemical reasoning.
"""

import re
from typing import List, Tuple

from src.models.reaction_record import ReactionRecord, TRACKED_FIELDS
from src.utils.text_utils import normalize_solvent, normalize_temperature
from src.utils.logging_utils import get_logger

logger = get_logger(__name__)

# Fields that MUST be non-NR for the record to be considered valid.
REQUIRED_FIELDS = ["donor_id", "acceptor_id", "product_id"]

# Basic plausibility checks: field → (pattern the value must NOT match, message)
IMPLAUSIBLE_PATTERNS: List[Tuple[str, str, str]] = [
    # yield should be a number between 0 and 100
    ("yield",       r'^\d+%$',          "yield does not look like a percentage"),
    # temperature should contain a number or 'room temperature'
    ("temperature", r'\d|room',         "temperature value looks unusual"),
]


def validate_and_normalize(record: ReactionRecord) -> ReactionRecord:
    """
    Validate and normalize *record* in place. Returns the same record.

    Steps performed:
    1. Normalize solvent and temperature strings.
    2. Run required-field checks.
    3. Run basic plausibility checks.
    4. Compute completeness_score and unresolved_fields.

    Parameters
    ----------
    record : ReactionRecord after fill_missing_fields().

    Returns
    -------
    The same ReactionRecord, updated in place.
    """
    _normalize_fields(record)
    issues = _check_required(record) + _check_plausibility(record)

    if issues:
        for issue in issues:
            logger.warning(f"Validation issue [{record.paper_id}]: {issue}")
    else:
        logger.info(f"Record {record.paper_id} passed all validation checks")

    record.compute_completeness()
    logger.info(
        f"Completeness: {record.completeness_score:.0%} | "
        f"Unresolved: {record.unresolved_fields}"
    )
    return record


# ── Internal helpers ──────────────────────────────────────────────────────────

def _normalize_fields(record: ReactionRecord) -> None:
    """Expand common abbreviations for solvent and temperature in place."""
    if record.solvent not in ("NR", ""):
        record.solvent = normalize_solvent(record.solvent)
    if record.temperature not in ("NR", ""):
        record.temperature = normalize_temperature(record.temperature)


def _check_required(record: ReactionRecord) -> List[str]:
    """Return a list of warning messages for missing required fields."""
    issues = []
    for field in REQUIRED_FIELDS:
        val = getattr(record, field, "NR")
        if val == "NR" or not val:
            issues.append(f"Required field '{field}' is NR")
    return issues


def _check_plausibility(record: ReactionRecord) -> List[str]:
    """Return warning messages for values that look chemically wrong."""
    issues = []
    field_map = {"yield": "yield_"}
    for field, pattern, message in IMPLAUSIBLE_PATTERNS:
        attr = field_map.get(field, field)
        val  = getattr(record, attr, "NR")
        if val and val != "NR":
            if not re.search(pattern, val, re.IGNORECASE):
                issues.append(f"Field '{field}' value '{val}': {message}")
    return issues
