"""
Figure/Table Extraction — run MERMaid (VisualHeist + DataRaider) on one paper.

Delegates to the MERMaid adapter (mock or real) and saves the raw output.
Accepts an optional *documents* dict from the Shared Input Layer so that
pdfplumber text extraction is not duplicated.

Architecture position
---------------------
Shared Input Layer → Figure/Table Extraction [MERMaid VisualHeist]
                  → Branch C figure outputs
"""

from pathlib import Path
from typing import Optional

from configs import settings
from src.adapters.mermaid_adapter import run_mermaid_on_paper
from src.models.paper import Paper
from src.utils.logging_utils import get_logger

logger = get_logger(__name__)


def run_mermaid(
    paper: Paper,
    output_dir: Optional[Path] = None,
    documents: Optional[dict] = None,
) -> dict:
    """
    Run MERMaid on *paper* and return the extraction result dict.

    Parameters
    ----------
    paper      : A registered Paper object.
    output_dir : Where to write the raw MERMaid output JSON.
                 Defaults to settings.MERMAID_OUTPUT_DIR.
    documents  : Optional output of load_documents() from the Shared Input Layer.
                 When provided, text_blocks/si_blocks are taken from here so
                 pdfplumber is not run a second time.

    Returns
    -------
    dict — the MERMaid extraction output (figures, tables, text_blocks, si_blocks).
    """
    output_dir = Path(output_dir or settings.MERMAID_OUTPUT_DIR)
    logger.info(f"Running MERMaid on paper {paper.paper_id}")

    result = run_mermaid_on_paper(
        paper_id   = paper.paper_id,
        pdf_path   = paper.pdf_path,
        si_path    = paper.si_path,
        output_dir = output_dir,
        documents  = documents,
    )
    logger.info(
        f"MERMaid done for {paper.paper_id}: "
        f"{len(result.get('figures', []))} figure(s), "
        f"{len(result.get('tables', []))} table(s), "
        f"{len(result.get('text_blocks', []))} text block(s)"
    )
    return result
