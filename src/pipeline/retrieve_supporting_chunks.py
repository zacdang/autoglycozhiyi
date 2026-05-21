"""
Step 8 — Retrieve supporting text chunks for missing fields.

Uses a simple hybrid retrieval strategy:
  1. Keyword match — does the chunk mention relevant field-specific terms?
  2. Identifier match — does the chunk mention the donor/acceptor/product IDs?

No embeddings or vector databases are used here.

TODO: Replace or augment with embedding-based semantic search (e.g. using
      sentence-transformers or OpenAI embeddings) for better recall.
"""

from typing import Dict, List

from src.models.reaction_record import ReactionRecord
from src.utils.text_utils import keyword_match_score
from src.utils.logging_utils import get_logger

logger = get_logger(__name__)

# Keywords associated with each field we might need to fill.
FIELD_KEYWORDS: Dict[str, List[str]] = {
    "promoter":       ["promoter", "NIS", "TfOH", "NBS", "Tf2O", "TMSOTf", "BSI", "activation"],
    "solvent":        ["solvent", "CH2Cl2", "DCM", "THF", "Et2O", "MeCN", "dissolved", "in anhydrous"],
    "temperature":    ["temperature", "°C", "degrees", "cooled", "warmed", "-20", "room temperature", "rt"],
    "time":           ["hour", "hours", "min", "minutes", "stirred for", "overnight"],
    "yield":          ["yield", "%", "afforded", "obtained", "isolated"],
    "stereochemistry":["anomer", "α", "β", "alpha", "beta", "selectivity", "ratio", "α/β"],
    "procedure_reference": ["procedure", "see SI", "supporting information", "general method"],
    "donor_name":     ["thioglycoside", "trichloroacetimidate", "imidate", "donor"],
    "acceptor_name":  ["acceptor", "alcohol", "free OH", "galactose", "glucose"],
    "product_name":   ["disaccharide", "oligosaccharide", "product", "afforded"],
}

# Maximum number of supporting chunks to return per field.
TOP_K = 3


def retrieve_supporting_chunks(
    record: ReactionRecord,
    unified: dict,
) -> Dict[str, List[str]]:
    """
    Find the most relevant text chunks for each field that is still "NR".

    Parameters
    ----------
    record  : Current (partially filled) ReactionRecord.
    unified : Merged extraction dict containing text_chunks and si_chunks.

    Returns
    -------
    dict mapping field_name → list of relevant chunk texts (up to TOP_K).
    """
    # Identify which fields still need filling.
    missing = [
        f for f in FIELD_KEYWORDS
        if getattr(record, f if f != "yield" else "yield_", "NR") == "NR"
    ]

    if not missing:
        logger.info("No missing fields — skipping chunk retrieval")
        return {}

    # Gather all available chunks.
    all_chunks: List[dict] = (
        unified.get("text_chunks", [])
        + unified.get("si_chunks", [])
    )

    # Build the set of identifiers to also scan for.
    id_hints = {
        record.donor_id, record.acceptor_id, record.product_id
    } - {"NR", ""}

    results: Dict[str, List[str]] = {}

    for field in missing:
        keywords = FIELD_KEYWORDS.get(field, [])
        scored: List[tuple] = []

        for chunk in all_chunks:
            text  = chunk.get("text", "")
            score = keyword_match_score(text, keywords)

            # Boost score if the chunk also mentions a relevant compound ID.
            for id_hint in id_hints:
                if id_hint and id_hint in text:
                    score += 0.2

            if score > 0:
                scored.append((score, text))

        # Sort by score descending, take top K.
        scored.sort(key=lambda x: x[0], reverse=True)
        results[field] = [text for _, text in scored[:TOP_K]]

        logger.debug(
            f"Field '{field}': retrieved {len(results[field])} chunk(s)"
        )

    logger.info(
        f"Retrieved supporting chunks for {len(results)} field(s): "
        f"{list(results.keys())}"
    )
    return results
