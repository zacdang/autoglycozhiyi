"""
Step 7 — Assign donor / acceptor / product roles and build an initial
         glycosylation reaction record.

Uses the MERMaid visual branch as the primary source for the initial reaction
record backbone (figures, captions, text labels, DataRaider reaction rows).
The CDE text branch is used only to fill condition mentions (promoter, solvent,
temperature, time, yield, stereochemistry) when the visual data is absent.

All unknown fields are initialised to "NR" (not reported).
"""

from typing import List, Optional

from src.models.reaction_record import ReactionRecord
from src.utils.logging_utils import get_logger
from src.utils.text_utils import extract_identifiers_from_text

logger = get_logger(__name__)

# Promoter keywords to scan for in text
PROMOTER_KEYWORDS = [
    "NIS", "TfOH", "NBS", "BSI", "DMTST", "Tf2O", "TTBP", "AgOTf",
    "TMSOTf", "BF3·Et2O", "Cu(OTf)2", "DDQ", "CAN",
]


def assign_roles(
    paper_id: str,
    relevant_figures: List[dict],
    unified: dict,
    id_dict: dict,
) -> ReactionRecord:
    """
    Build an initial ReactionRecord from the best available figure and conditions.

    Parameters
    ----------
    paper_id          : ID of the paper being processed.
    relevant_figures  : Output of classify_relevant_figures() — sorted by confidence.
    unified           : Merged extraction dict.
    id_dict           : Output of build_identifier_dictionary().

    Returns
    -------
    ReactionRecord with as many fields filled as possible; unknowns = "NR".
    """
    record = ReactionRecord(paper_id=paper_id)

    if not relevant_figures:
        logger.warning(f"No relevant figures found for {paper_id}; record will be mostly NR")
        return record

    # Use the highest-confidence relevant figure as the primary source.
    best_fig = relevant_figures[0]
    record.figure_id = best_fig["figure_id"]

    # ── Extract participant IDs from the figure ───────────────────────────────
    caption_text = best_fig.get("caption", "")
    label_text   = " ".join(best_fig.get("text_labels", []))
    combined     = caption_text + " " + label_text

    donor_id, acceptor_id, product_id = _extract_participants(
        combined, id_dict
    )
    record.donor_id    = donor_id    or "NR"
    record.acceptor_id = acceptor_id or "NR"
    record.product_id  = product_id  or "NR"

    # ── Look up names from the identifier dictionary ──────────────────────────
    resolved = id_dict.get("resolved", {})
    if record.donor_id != "NR":
        record.donor_name = resolved.get(record.donor_id, {}).get("possible_name", "NR")
    if record.acceptor_id != "NR":
        record.acceptor_name = resolved.get(record.acceptor_id, {}).get("possible_name", "NR")
    if record.product_id != "NR":
        record.product_name = resolved.get(record.product_id, {}).get("possible_name", "NR")

    # ── Fill conditions from CDE text branch condition mentions ──────────────
    # CDE is used here only to supplement visual data that is absent from the
    # MERMaid branch (figures / DataRaider rows).
    for mention in unified.get("condition_mentions", []):
        field = mention.get("field", "")
        value = mention.get("value", "NR")
        ctx   = mention.get("context", "")
        if field == "temperature"  and record.temperature   == "NR":
            record.temperature   = value
            record.provenance["temperature"]   = ctx
        elif field == "time"       and record.time          == "NR":
            record.time          = value
            record.provenance["time"]          = ctx
        elif field == "yield"      and record.yield_        == "NR":
            record.yield_        = value
            record.provenance["yield"]         = ctx
        elif field == "stereochemistry" and record.stereochemistry == "NR":
            record.stereochemistry = value
            record.provenance["stereochemistry"] = ctx

    # ── Extract promoter from CDE text branch chemical mentions ──────────────
    promoter_parts = []
    for chem in unified.get("chemical_mentions", []):
        if chem.get("role_guess") == "promoter":
            promoter_parts.append(chem.get("text", ""))
    if promoter_parts:
        record.promoter = "/".join(promoter_parts)
        record.provenance["promoter"] = "CDE chemical_mentions"

    # ── Extract solvent from CDE text branch chemical mentions ───────────────
    for chem in unified.get("chemical_mentions", []):
        if chem.get("role_guess") == "solvent" and record.solvent == "NR":
            record.solvent = chem.get("full_name") or chem.get("text", "NR")
            record.provenance["solvent"] = "CDE chemical_mentions"

    # ── Look for procedure reference in caption ───────────────────────────────
    import re
    proc_match = re.search(r'\bProcedure\s+[A-Z]\b', combined, re.IGNORECASE)
    if proc_match:
        record.procedure_reference = proc_match.group(0)
        record.provenance["procedure_reference"] = f"Figure {record.figure_id} caption"

    # ── Populate reaction_rows from DataRaider tables (MERMaid visual branch) ─
    all_rows = []
    for table in unified.get("tables", []):
        if table.get("source") != "dataraider":
            continue
        table_id = table.get("table_id", "")
        for row in table.get("rows", []):
            all_rows.append({"table_id": table_id, **row})
    record.reaction_rows = all_rows

    # ── Backfill conditions from DataRaider rows when still NR ───────────────
    for row in all_rows:
        row_lower = {k.lower(): v for k, v in row.items()}
        if record.temperature == "NR" and row_lower.get("temperature"):
            record.temperature = row_lower["temperature"]
            record.provenance["temperature"] = "dataraider_table"
        if record.yield_ == "NR" and row_lower.get("yield"):
            record.yield_ = row_lower["yield"]
            record.provenance["yield"] = "dataraider_table"
        if record.time == "NR" and row_lower.get("time"):
            record.time = row_lower["time"]
            record.provenance["time"] = "dataraider_table"
        if record.promoter == "NR" and row_lower.get("promoter"):
            record.promoter = row_lower["promoter"]
            record.provenance["promoter"] = "dataraider_table"
        if record.solvent == "NR" and row_lower.get("solvent"):
            record.solvent = row_lower["solvent"]
            record.provenance["solvent"] = "dataraider_table"
        if record.donor_id == "NR" and row_lower.get("donor"):
            record.donor_id = record.donor_name = row_lower["donor"]
            record.provenance["donor_id"] = "dataraider_table"
        if record.acceptor_id == "NR" and row_lower.get("acceptor"):
            record.acceptor_id = record.acceptor_name = row_lower["acceptor"]
            record.provenance["acceptor_id"] = "dataraider_table"
        if record.product_id == "NR" and row_lower.get("product"):
            record.product_id = record.product_name = row_lower["product"]
            record.provenance["product_id"] = "dataraider_table"
        if record.stereochemistry == "NR" and row_lower.get("stereochemistry"):
            record.stereochemistry = row_lower["stereochemistry"]
            record.provenance["stereochemistry"] = "dataraider_table"

    logger.info(
        f"Role assignment for {paper_id}: "
        f"donor={record.donor_id}, acceptor={record.acceptor_id}, "
        f"product={record.product_id}, promoter={record.promoter}, "
        f"reaction_rows={len(record.reaction_rows)}"
    )
    return record


# ── Internal helpers ──────────────────────────────────────────────────────────

def _extract_participants(
    text: str, id_dict: dict
) -> tuple:
    """
    Attempt to identify donor, acceptor, and product from *text* using
    the identifier dictionary's role_guess field.

    Returns (donor_id, acceptor_id, product_id) — any may be None.
    """
    labels = extract_identifiers_from_text(text)
    resolved   = id_dict.get("resolved", {})
    unresolved = id_dict.get("unresolved", {})
    all_ids    = {**resolved, **unresolved}

    donor_id = acceptor_id = product_id = None

    for label in labels:
        entry = all_ids.get(label, {})
        role  = entry.get("role_guess", "unknown")
        if role == "donor"    and donor_id    is None:
            donor_id    = label
        elif role == "acceptor" and acceptor_id is None:
            acceptor_id = label
        elif role == "product"  and product_id  is None:
            product_id  = label

    # If roles could not be determined from id_dict, fall back to positional
    # heuristic: first label = donor, second = acceptor, third = product.
    if labels and donor_id is None:
        donor_id = labels[0]
    if len(labels) > 1 and acceptor_id is None:
        acceptor_id = labels[1]
    if len(labels) > 2 and product_id is None:
        product_id = labels[2]

    return donor_id, acceptor_id, product_id
