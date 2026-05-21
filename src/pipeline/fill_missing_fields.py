"""
Main Merge / Fusion Node — fill missing fields using all three extraction sources.

This is the main merge point in the canonical workflow. It accepts:
- figure-derived record (from assign_roles via MERMaid DataRaider)
- supporting_chunks (retrieved per-field)
- text_org (Branch A: CDE + Agent AI classified text chunks)
- id_dict  (Branch B: CDE + Agent AI identifier dictionary)

In mock mode: rule-based regex extraction (unchanged, for test stability).
In real mode: regex first, then OpenAI GPT-4o for any still-NR fields,
              drawing context from all three branches.

Architecture position
---------------------
INCOMPLETE → Fill Missing Fields (main MERGE node) [Agent AI]
             ← merges: figure-derived record
                       + Branch A text chunks
                       + Branch B identifier dict
→ loop back to Completeness Check
"""

import re
from typing import Dict, List, Optional

from configs import settings
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
    text_org: Optional[dict] = None,
    id_dict: Optional[dict] = None,
) -> ReactionRecord:
    """
    Attempt to fill NR fields in *record* using all available sources.

    Parameters
    ----------
    record            : Partially filled ReactionRecord from assign_roles().
    supporting_chunks : Dict from retrieve_supporting_chunks() mapping
                        field_name → list of relevant chunk texts.
    text_org          : Optional output of run_text_organisation() (Branch A).
                        Provides classified text chunks for richer context.
    id_dict           : Optional output of run_identifier_dictionary() (Branch B).
                        Provides resolved identifier → name mappings.

    Returns
    -------
    The same ReactionRecord with as many NR fields filled as possible.
    """
    # ── Step 1: Rule-based regex extraction from supporting_chunks ────────────
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

    # ── Step 2: Backfill names from identifier dictionary (Branch B) ──────────
    if id_dict:
        _backfill_from_id_dict(record, id_dict)

    # ── Step 3: Real-mode LLM fill for still-NR fields ────────────────────────
    if settings.PIPELINE_MODE == "real":
        _fill_with_llm(record, supporting_chunks, text_org, id_dict)

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


def _backfill_from_id_dict(record: ReactionRecord, id_dict: dict) -> None:
    """
    Use Branch B's identifier dictionary to fill donor/acceptor/product names
    that are still NR.
    """
    resolved = id_dict.get("resolved", {})
    if record.donor_id != "NR" and record.donor_name == "NR":
        name = resolved.get(record.donor_id, {}).get("possible_name", "")
        if name:
            record.donor_name = name
            record.provenance["donor_name"] = "id_dict_branch_b"
    if record.acceptor_id != "NR" and record.acceptor_name == "NR":
        name = resolved.get(record.acceptor_id, {}).get("possible_name", "")
        if name:
            record.acceptor_name = name
            record.provenance["acceptor_name"] = "id_dict_branch_b"
    if record.product_id != "NR" and record.product_name == "NR":
        name = resolved.get(record.product_id, {}).get("possible_name", "")
        if name:
            record.product_name = name
            record.provenance["product_name"] = "id_dict_branch_b"


def _fill_with_llm(
    record: ReactionRecord,
    supporting_chunks: Dict[str, List[str]],
    text_org: Optional[dict],
    id_dict: Optional[dict],
) -> None:
    """
    Real-mode Agent AI fill.

    For each field still NR, call GPT-4o with context from all three sources:
    1. figure-derived supporting_chunks
    2. Branch A text_org chunks (synthesis_procedures, general_procedures)
    3. Branch B id_dict resolved entries

    Only called when PIPELINE_MODE == "real".
    """
    from src.models.reaction_record import TRACKED_FIELDS

    still_nr = [
        f for f in TRACKED_FIELDS
        if getattr(record, "yield_" if f == "yield" else f, "NR") == "NR"
    ]
    if not still_nr:
        return

    if not settings.OPENAI_API_KEY:
        logger.warning("[fill_missing_fields] OPENAI_API_KEY not set — skipping LLM fill")
        return

    try:
        from openai import OpenAI
        import json as _json
        client = OpenAI(api_key=settings.OPENAI_API_KEY)
    except ImportError:
        logger.warning("[fill_missing_fields] openai not installed — skipping LLM fill")
        return

    # Build a rich context from all three branches.
    context_parts = []

    # Figure-derived chunks.
    for field, chunks in supporting_chunks.items():
        for c in chunks[:2]:
            context_parts.append(c[:200])

    # Branch A classified text chunks.
    if text_org:
        for cat in ("synthesis_procedures", "general_procedures"):
            for chunk in text_org.get(cat, [])[:3]:
                context_parts.append(chunk.get("text", "")[:200])

    # Branch B identifier entries.
    if id_dict:
        for label, entry in list(id_dict.get("resolved", {}).items())[:10]:
            name = entry.get("possible_name", "")
            if name:
                context_parts.append(f"{label}: {name}")

    context = "\n".join(context_parts)[:3000]

    fields_desc = ", ".join(still_nr)
    prompt = (
        f"You are a chemistry expert extracting data from a glycosylation paper.\n"
        f"Based on the context below, fill in the following fields: {fields_desc}.\n"
        f"Reply with a JSON object where keys are field names and values are the "
        f"extracted values (or null if not found).\n\n"
        f"Context:\n{context}\n\n"
        f"Current known values: "
        f"donor_id={record.donor_id}, acceptor_id={record.acceptor_id}, "
        f"promoter={record.promoter}, solvent={record.solvent}"
    )

    try:
        resp = client.chat.completions.create(
            model="gpt-4o",
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"},
            max_tokens=300,
        )
        result = _json.loads(resp.choices[0].message.content)

        for field in still_nr:
            attr = "yield_" if field == "yield" else field
            value = result.get(field)
            if value and value != "null" and isinstance(value, str):
                if field == "solvent":
                    value = normalize_solvent(value)
                elif field == "temperature":
                    value = normalize_temperature(value)
                setattr(record, attr, value)
                record.provenance[field] = "llm_fill_missing_fields"
                logger.debug(f"[fill_missing_fields] LLM filled '{field}' = '{value}'")

    except Exception as exc:
        logger.error(f"[fill_missing_fields] LLM call failed: {exc}")
