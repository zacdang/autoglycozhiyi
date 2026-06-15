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


# ── Module 1 input validation ────────────────────────────────────────────────

def validate_input_metadata(
    paper,
    check_files: bool = True,
    require_si: bool = False,
) -> dict:
    """
    Validate the paper metadata and input files before downstream modules run.

    This is a lightweight Module 1 quality-control check. It is intentionally
    non-destructive: the function returns a report instead of raising, so the
    pipeline can decide whether to continue, warn, or stop later.

    Parameters
    ----------
    paper : object
        Paper-like object with paper_id, pdf_path, and optional si_path.
    check_files : bool
        If True, verify that configured PDF paths exist, have .pdf suffixes,
        and are not empty. In mock mode this should usually be False.
    require_si : bool
        If True, missing SI paths are treated as errors. Otherwise they are
        warnings because some papers may not have a separate SI file.

    Returns
    -------
    dict with keys:
        paper_id : str | None
        valid    : bool
        errors   : list[str]
        warnings : list[str]
        checked_paths : dict
    """
    errors = []
    warnings = []

    paper_id = getattr(paper, "paper_id", None)
    pdf_path = getattr(paper, "pdf_path", None)
    si_path = getattr(paper, "si_path", None)

    if not paper_id:
        errors.append("Missing required metadata field: paper_id")

    if not pdf_path:
        errors.append("Missing required metadata field: pdf_path")
    elif check_files:
        _validate_pdf_path(pdf_path, label="main PDF", errors=errors, warnings=warnings)

    if not si_path:
        message = "Missing optional metadata field: si_path"
        if require_si:
            errors.append(message)
        else:
            warnings.append(message)
    elif check_files:
        _validate_pdf_path(si_path, label="SI PDF", errors=errors, warnings=warnings)

    return {
        "paper_id": paper_id,
        "valid": not errors,
        "errors": errors,
        "warnings": warnings,
        "checked_paths": {
            "pdf_path": str(pdf_path) if pdf_path else None,
            "si_path": str(si_path) if si_path else None,
        },
    }


def _validate_pdf_path(path_value: str, label: str, errors: list, warnings: list) -> None:
    """Append validation messages for a configured PDF path."""
    path = Path(path_value)

    if path.suffix.lower() != ".pdf":
        warnings.append(f"{label} path does not have a .pdf extension: {path_value}")

    if not path.exists():
        errors.append(f"{label} not found: {path_value}")
        return

    if not path.is_file():
        errors.append(f"{label} path is not a file: {path_value}")
        return

    try:
        if path.stat().st_size == 0:
            errors.append(f"{label} is empty: {path_value}")
    except OSError as exc:
        errors.append(f"Could not inspect {label}: {path_value} ({exc})")


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
        input_validation: Module 1 validation report for metadata and file paths
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

    input_validation = validate_input_metadata(
        paper,
        check_files=(settings.PIPELINE_MODE != "mock"),
        require_si=False,
    )
    _log_input_validation(input_validation)

    if settings.PIPELINE_MODE == "mock":
        # In mock mode the MERMaid adapter serves synthetic data; no real PDF needed.
        logger.info(f"[load_documents] mock mode — skipping pdfplumber for {paper_id}")
        return {
            "paper_id":   paper_id,
            "pdf_path":   pdf_path,
            "si_path":    si_path,
            "text_blocks": [],
            "si_blocks":   [],
            "input_validation": input_validation,
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
        "input_validation": input_validation,
    }


def _log_input_validation(report: dict) -> None:
    """Log Module 1 validation results without stopping the pipeline."""
    paper_id = report.get("paper_id") or "unknown_paper"

    if report.get("valid"):
        logger.info(f"[load_documents] input validation passed for {paper_id}")
    else:
        logger.warning(f"[load_documents] input validation found issue(s) for {paper_id}")

    for message in report.get("errors", []):
        logger.error(f"[load_documents] validation error: {message}")
    for message in report.get("warnings", []):
        logger.warning(f"[load_documents] validation warning: {message}")


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
