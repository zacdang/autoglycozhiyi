"""
Step 9 — Fill missing fields using retrieved supporting chunks.

Uses deterministic, rule-based extraction (regex) from the top-ranked chunks.
Tracks provenance for every field that gets filled.

TODO: Add an LLM call here using configs/prompts/fill_missing_fields.txt
      for fields that the rule-based logic cannot resolve.
"""

import re
from typing import Dict, List

from src.models.reaction_record import ReactionRecord
from src.utils.text_utils import normalize_solvent, normalize_temperature
from src.utils.logging_utils import get_logger

logger = get_logger(__name__)

# ── Regex patterns for each field ────────────────────────────────────────────
# Each pattern should have at least one capture group.

PATTERNS: Dict[str, List[str]] = {
    "temperature": [
        r'(-?\d+\s*°C)',                   # e.g. -20 °C
        r'(room\s+temperature|r\.?t\.?)',   # rt / r.t.
    ],
    "time": [
        r'(\d+(?:\.\d+)?\s*h(?:ours?)?)',   # 2 h / 2 hours
        r'(\d+\s+min(?:utes?)?)',            # 30 min
        r'(overnight)',
    ],
    "yield": [
        r'(\d+(?:\.\d+)?\s*%)',             # 78%
    ],
    "stereochemistry": [
        r'(α/β\s*[>≥<≤]?\s*\d+:\d+)',      # α/β > 1:20
        r'(β-anomer|α-anomer)',
        r'\b(alpha|beta)\b',
    ],
    "solvent": [
        r'\bin\s+(CH2Cl2|DCM|THF|Et2O|MeOH|EtOH|MeCN|toluene|benzene|DMSO|DMF)\b',
    ],
    "promoter": [
        r'\b(NIS/TfOH|NIS|TfOH|Tf2O/TTBP|BSI|DMTST|TMSOTf|BF3[·•·]Et2O|AgOTf)\b',
    ],
    "procedure_reference": [
        r'(Procedure\s+[A-Z])',
        r'(see\s+(?:supporting\s+information|SI)(?:,\s*[Ss]ection\s*\d+)?)',
    ],
}


def fill_missing_fields(
    record: ReactionRecord,
    supporting_chunks: Dict[str, List[str]],
) -> ReactionRecord:
    """
    Attempt to fill NR fields in *record* using *supporting_chunks*.

    Parameters
    ----------
    record            : Partially filled ReactionRecord from assign_roles().
    supporting_chunks : Dict from retrieve_supporting_chunks() mapping
                        field_name → list of relevant chunk texts.

    Returns
    -------
    The same ReactionRecord with as many NR fields filled as possible.
    """
    for field, chunks in supporting_chunks.items():
        attr = "yield_" if field == "yield" else field
        if getattr(record, attr, "NR") != "NR":
            continue  # already filled

        value, source = _extract_from_chunks(field, chunks)
        if value:
            # Normalise common forms before storing.
            if field == "solvent":
                value = normalize_solvent(value)
            elif field == "temperature":
                value = normalize_temperature(value)

            setattr(record, attr, value)
            record.provenance[field] = source
            logger.debug(f"Filled '{field}' = '{value}' from: {source[:80]}")
        else:
            # TODO: Insert an LLM call here using fill_missing_fields.txt
            #       to handle cases the regex cannot cover.
            pass

    # Attach supporting chunk texts to the record for transparency.
    for chunks in supporting_chunks.values():
        for text in chunks:
            if text not in record.supporting_chunks:
                record.supporting_chunks.append(text)

    return record


# ── Internal helpers ──────────────────────────────────────────────────────────

def _extract_from_chunks(
    field: str, chunks: List[str]
) -> tuple:
    """
    Apply regex patterns for *field* against each chunk.
    Returns (value, source_snippet) or ("", "") if nothing matched.
    """
    patterns = PATTERNS.get(field, [])
    for chunk_text in chunks:
        for pat in patterns:
            m = re.search(pat, chunk_text, re.IGNORECASE)
            if m:
                return m.group(1).strip(), chunk_text[:200]
    return "", ""
