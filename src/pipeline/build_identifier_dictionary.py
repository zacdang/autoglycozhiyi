"""
Step 6 — Build an identifier dictionary.

Primarily uses the CDE text branch (text_chunks, si_chunks) to map
alphanumeric compound labels (e.g. "3a", "5b", "Procedure B") to chemical
names or descriptions.  Figure captions from the MERMaid visual branch are
used as a secondary source when no name can be resolved from the text chunks.

CDE text chunks (source_type in {"procedure", "main_text", "si_text"}) are
ordered before MERMaid caption chunks (source_type == "caption") so that the
first context seen for any label is preferentially from the CDE text branch.

Output structure:
{
  "resolved":   { "3a": Identifier.to_dict(), ... },
  "unresolved": { "6c": Identifier.to_dict(), ... }
}
"""

from typing import Dict, List, Tuple

from src.models.identifier import Identifier
from src.utils.text_utils import extract_identifiers_from_text
from src.utils.logging_utils import get_logger

logger = get_logger(__name__)

# Heuristics: if any of these phrases appear near an identifier, guess its role.
DONOR_HINTS    = ["donor", "thioglycoside", "trichloroacetimidate", "imidate", "glycosyl donor"]
ACCEPTOR_HINTS = ["acceptor", "acceptor alcohol", "free oh", "free 4-oh", "free 3-oh"]
PRODUCT_HINTS  = ["product", "disaccharide", "oligosaccharide", "afforded", "obtained"]


def build_identifier_dictionary(unified: dict) -> dict:
    """
    Build a dictionary of compound identifiers from the merged extraction.

    Parameters
    ----------
    unified : The merged extraction dict from merge_extractions().

    Returns
    -------
    dict with two keys:
      "resolved"   : identifiers for which a name/description was found.
      "unresolved" : identifiers found but not yet linked to a chemical name.
    """
    # CDE text branch chunks (procedures, main text, SI text) are listed first
    # so they take priority as the representative context for any label.
    # MERMaid visual branch caption chunks are appended afterward as a
    # secondary source.
    cde_chunks: List[dict] = (
        unified.get("text_chunks", [])
        + unified.get("si_chunks", [])
    )
    # Sort within the CDE chunks: procedure > main_text/si_text > anything else
    _CDE_SOURCE_ORDER = {"procedure": 0, "main_text": 1, "si_text": 1}
    cde_chunks = sorted(
        cde_chunks,
        key=lambda c: _CDE_SOURCE_ORDER.get(c.get("source_type", ""), 2),
    )

    # Figure captions from the MERMaid visual branch — used as secondary source.
    caption_chunks: List[dict] = []
    for fig in unified.get("figures", []):
        caption = fig.get("caption", "")
        labels  = " ".join(fig.get("text_labels", []))
        if caption or labels:
            caption_chunks.append({
                "chunk_id":    f"cap_{fig['figure_id']}",
                "text":        f"{caption} {labels}",
                "source_type": "caption",
            })

    # CDE chunks come first; MERMaid caption chunks are secondary.
    all_chunks: List[dict] = cde_chunks + caption_chunks

    # Collect raw labels from every chunk.
    raw_label_to_contexts: Dict[str, List[Tuple[str, str]]] = {}
    for chunk in all_chunks:
        text        = chunk.get("text", "")
        source_type = chunk.get("source_type", "main_text")
        labels      = extract_identifiers_from_text(text)
        for label in labels:
            raw_label_to_contexts.setdefault(label, []).append((text, source_type))

    resolved   = {}
    unresolved = {}

    for label, contexts in raw_label_to_contexts.items():
        # Use the first context that mentions the label as representative.
        source_text, source_type = contexts[0]

        possible_name, confidence = _try_resolve_name(label, source_text, all_chunks)
        role_guess = _guess_role(source_text)

        identifier = Identifier(
            identifier    = label,
            possible_name = possible_name,
            source_text   = source_text[:300],  # truncate for readability
            source_type   = source_type,
            confidence    = confidence,
            resolved      = bool(possible_name),
            role_guess    = role_guess,
        )

        if identifier.resolved:
            resolved[label]   = identifier.to_dict()
        else:
            unresolved[label] = identifier.to_dict()

    logger.info(
        f"Identifier dictionary: {len(resolved)} resolved, "
        f"{len(unresolved)} unresolved"
    )
    return {"resolved": resolved, "unresolved": unresolved}


# ── Internal helpers ──────────────────────────────────────────────────────────

def _try_resolve_name(
    label: str, source_text: str, all_chunks: List[dict]
) -> Tuple[str, float]:
    """
    Search through chunks for a descriptive sentence that names *label*.
    Returns (name_string, confidence) — ("", 0.0) if nothing found.
    """
    # Look for patterns like "Compound 3a was prepared as X" or "3a is a X"
    import re
    patterns = [
        rf'{re.escape(label)}\s+(?:is|was|as)\s+(?:a\s+|an\s+)?([^\.;,]{{5,80}})',
        rf'(?:compound|donor|acceptor|product)\s+{re.escape(label)}\s*[,:\s]+([^\.;]{{5,80}})',
    ]
    for chunk in all_chunks:
        text = chunk.get("text", "")
        for pat in patterns:
            m = re.search(pat, text, re.IGNORECASE)
            if m:
                return m.group(1).strip(), 0.8

    return "", 0.0


def _guess_role(text: str) -> str:
    """Return a coarse role guess based on surrounding text keywords."""
    text_lower = text.lower()
    for hint in DONOR_HINTS:
        if hint in text_lower:
            return "donor"
    for hint in ACCEPTOR_HINTS:
        if hint in text_lower:
            return "acceptor"
    for hint in PRODUCT_HINTS:
        if hint in text_lower:
            return "product"
    return "unknown"
