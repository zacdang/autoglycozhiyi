"""
CDE Runner — run ChemDataExtractor on the paper's main text and SI text.

CDE is now parallel to MERMaid (not downstream). It receives text_blocks
directly from the Shared Input Layer via the *documents* parameter, rather
than from the MERMaid branch output.

This function is called by run_text_organisation.py (Branch A) and
run_identifier_dictionary.py (Branch B). It can still be called standalone
for backward compatibility.

Architecture position
---------------------
Shared Input Layer → Branch A: Text Organisation [CDE primary + Agent AI]
                  → Branch B: Identifier Dictionary [CDE candidates + Agent AI]
"""

from pathlib import Path
from typing import Optional

from configs import settings
from src.adapters.chemdataextractor_adapter import parse_main_text, parse_si_text
from src.models.paper import Paper
from src.utils.logging_utils import get_logger

logger = get_logger(__name__)


def run_chemdataextractor(
    paper: Paper,
    documents: Optional[dict] = None,
    mermaid_output: Optional[dict] = None,
) -> dict:
    """
    Run ChemDataExtractor (CDE) on *paper* (main text + SI).

    CDE is now parallel to MERMaid. Text blocks come from the Shared Input Layer
    via *documents*, not from the MERMaid branch.

    Parameters
    ----------
    paper          : A registered Paper object.
    documents      : Optional output of load_documents() from the Shared Input Layer.
                     When provided, text_blocks and si_blocks are passed directly to
                     the CDE adapter. Takes priority over mermaid_output.
    mermaid_output : Kept for backward compatibility. Used only when *documents* is
                     not provided. Will be removed in a future version.

    Returns
    -------
    dict with keys:
        paper_id, chemical_mentions, condition_mentions,
        procedure_blocks, text_chunks
    The SI results are merged into the same structure with a "_si" prefix
    on chunk_ids so they can be distinguished downstream.
    """
    logger.info(f"Running ChemDataExtractor on paper {paper.paper_id}")

    # Resolve text_blocks source: prefer Shared Input Layer documents.
    text_blocks: Optional[list] = None
    si_blocks:   Optional[list] = None

    if documents is not None:
        text_blocks = documents.get("text_blocks") or None
        si_blocks   = documents.get("si_blocks") or None
    elif mermaid_output is not None:
        # Backward-compatible fallback.
        text_blocks = mermaid_output.get("text_blocks") or None
        si_blocks   = mermaid_output.get("si_blocks") or None

    main_result = parse_main_text(
        paper_id    = paper.paper_id,
        text_path   = paper.pdf_path,
        text_blocks = text_blocks,
    )

    si_result = parse_si_text(
        paper_id    = paper.paper_id,
        text_path   = paper.si_path,
        text_blocks = si_blocks,
    )

    # Merge main + SI results into a single dict.
    # SI chunks get a "_si" prefix on their chunk_ids for traceability.
    merged = {
        "paper_id":          paper.paper_id,
        "chemical_mentions": main_result.get("chemical_mentions", [])
                           + si_result.get("chemical_mentions", []),
        "condition_mentions":main_result.get("condition_mentions", [])
                           + si_result.get("condition_mentions", []),
        "procedure_blocks":  main_result.get("procedure_blocks", [])
                           + _prefix_ids(si_result.get("procedure_blocks", []), "si_"),
        "text_chunks":       main_result.get("text_chunks", [])
                           + _prefix_ids(si_result.get("text_chunks", []), "si_"),
    }

    logger.info(
        f"CDE done for {paper.paper_id}: "
        f"{len(merged['chemical_mentions'])} chemical mention(s), "
        f"{len(merged['condition_mentions'])} condition mention(s)"
    )
    return merged


def _prefix_ids(items: list, prefix: str) -> list:
    """Add a prefix to block_id / chunk_id fields to avoid collisions."""
    for item in items:
        for key in ("block_id", "chunk_id"):
            if key in item:
                item[key] = prefix + item[key]
    return items
