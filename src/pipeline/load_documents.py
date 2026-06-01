"""
Shared Input Layer — loads raw document content for all pipeline branches.

This module is the single entry point for reading PDFs. Both the MERMaid
visual branch and the CDE text branch receive their text from here so that
pdfplumber extraction is performed exactly once per run.

Architecture position
---------------------
Shared Input Layer (Main PDF + SI PDF)
→ supplies text_blocks / si_blocks to:
    - MERMaid VisualHeist / DataRaider  (figures, tables)
    - Branch A: run_text_organisation   (CDE + Agent AI)
    - Branch B: run_identifier_dictionary (CDE + Agent AI)
"""

from pathlib import Path
from typing import Optional

from configs import settings
from src.utils.logging_utils import get_logger

logger = get_logger(__name__)


def load_documents(paper) -> dict:
    """
    Shared input layer — loads raw document content used by all branches.

    Extracts paragraph-level text blocks from the main PDF and (optionally)
    the supplementary information PDF using pdfplumber.

    In mock mode, text_blocks and si_blocks are returned as empty lists because
    the mock MERMaid sample already contains synthetic text blocks.

    Parameters
    ----------
    paper : A Paper object with pdf_path, si_path, and paper_id attributes.

    Returns
    -------
    dict with keys:
        paper_id   : str
        pdf_path   : str
        si_path    : str | None
        text_blocks: list of text-block dicts from the main PDF
        si_blocks  : list of text-block dicts from the SI PDF (empty if no SI)
    """
    paper_id = paper.paper_id
    pdf_path = paper.pdf_path
    si_path  = getattr(paper, "si_path", None)

    logger.info(f"[load_documents] Loading documents for {paper_id}")

    # Auto-download missing PDFs (tries direct download; prints manual link if blocked)
    try:
        from src.utils.download_papers import ensure_pdfs
        ensure_pdfs(paper)
        # Refresh paths in case ensure_pdfs updated them
        pdf_path = paper.pdf_path
        si_path  = getattr(paper, "si_path", None)
    except Exception as _dl_exc:
        logger.debug(f"[load_documents] PDF auto-download skipped: {_dl_exc}")

    if settings.PIPELINE_MODE == "mock":
        # In mock mode the MERMaid adapter serves synthetic data; no real PDF needed.
        logger.info(f"[load_documents] mock mode — skipping pdfplumber for {paper_id}")
        return {
            "paper_id":   paper_id,
            "pdf_path":   pdf_path,
            "si_path":    si_path,
            "text_blocks": [],
            "si_blocks":   [],
        }

    # Real mode: extract text blocks with pdfplumber.
    text_blocks = _extract_text_blocks(pdf_path, paper_id, prefix="BLK")
    si_blocks   = _extract_text_blocks(si_path,  paper_id, prefix="SI_BLK") if si_path else []

    logger.info(
        f"[load_documents] {paper_id}: "
        f"{len(text_blocks)} text block(s), {len(si_blocks)} SI block(s)"
    )

    return {
        "paper_id":   paper_id,
        "pdf_path":   pdf_path,
        "si_path":    si_path,
        "text_blocks": text_blocks,
        "si_blocks":   si_blocks,
    }


# ── pdfplumber extraction (moved from mermaid_adapter) ───────────────────────

def _extract_text_blocks(
    pdf_path: Optional[str],
    paper_id: str,
    prefix: str = "BLK",
    min_chars: int = 80,
) -> list:
    """
    Extract paragraph-level text blocks from a PDF using pdfplumber.

    Each page is split on double-newlines to approximate paragraph boundaries.
    Short fragments (< min_chars) are dropped as noise.

    Returns a list of text-block dicts matching our Chunk format:
        { block_id, page, text, section }
    """
    if not pdf_path or not Path(pdf_path).exists():
        logger.warning(f"[load_documents] PDF not found for text extraction: {pdf_path}")
        return []

    import pdfplumber

    blocks = []
    block_idx = 0

    try:
        with pdfplumber.open(pdf_path) as pdf:
            for page_num, page in enumerate(pdf.pages, start=1):
                raw_text = page.extract_text() or ""
                # Split on blank lines to approximate paragraphs.
                paragraphs = [p.strip() for p in raw_text.split("\n\n") if p.strip()]
                for para in paragraphs:
                    if len(para) < min_chars:
                        continue
                    blocks.append({
                        "block_id": f"{prefix}_{block_idx:04d}",
                        "page":     page_num,
                        "text":     para,
                        "section":  None,   # section detection not implemented yet
                    })
                    block_idx += 1
    except Exception as exc:
        logger.error(f"[load_documents] pdfplumber failed on {pdf_path}: {exc}")

    return blocks
