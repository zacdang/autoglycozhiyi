"""
Adapter for ChemDataExtractor (CDE) — chemistry-aware text/table parser.

Modes
-----
mock : Load pre-built sample JSON from data/samples/. No CDE installation needed.
real : Placeholder functions showing where ChemDataExtractor Python API calls go.
       Switch by setting PIPELINE_MODE=real in your .env file.

CDE conceptual output structure
--------------------------------
{
  "paper_id": str,
  "chemical_mentions": [
      { text, full_name, role_guess, context }
  ],
  "condition_mentions": [
      { field, value, context }
  ],
  "procedure_blocks": [
      { block_id, label, text }
  ],
  "text_chunks": [
      { chunk_id, text, section }
  ]
}
"""

from pathlib import Path
from typing import Optional

from configs import settings
from src.utils.json_utils import load_json, save_json
from src.utils.logging_utils import get_logger

logger = get_logger(__name__)


# ── Public API ────────────────────────────────────────────────────────────────

def parse_main_text(
    paper_id: str,
    text_path: Optional[str] = None,
    text_blocks: Optional[list] = None,
) -> dict:
    """
    Parse the main paper text with ChemDataExtractor (CDE text branch).

    In mock mode, loads sample CDE output.
    In real mode, calls the CDE Python API on the provided text file or uses
    pre-extracted *text_blocks* passed from the MERMaid branch.

    Parameters
    ----------
    paper_id    : Used to label the output file.
    text_path   : Path to the extracted plain-text file of the main paper body.
                  Only used in real mode when *text_blocks* is None.
    text_blocks : List of text-block dicts already produced by the MERMaid
                  branch. When provided, the adapter uses them directly without
                  re-reading from disk.

    Returns
    -------
    dict with keys: paper_id, chemical_mentions, condition_mentions,
                    procedure_blocks, text_chunks
    """
    if settings.PIPELINE_MODE == "mock":
        return _load_mock(paper_id, source="main")
    else:
        return _parse_real(paper_id, text_path, source="main", text_blocks=text_blocks)


def parse_si_text(
    paper_id: str,
    text_path: Optional[str] = None,
    text_blocks: Optional[list] = None,
) -> dict:
    """
    Parse the supplementary information (SI) text with ChemDataExtractor
    (CDE text branch).

    In mock mode, returns the same sample CDE output (SI-specific mock can be
    added to data/samples/ later).

    Parameters
    ----------
    paper_id    : Used to label the output file.
    text_path   : Path to the SI PDF / text file.  Used only when
                  *text_blocks* is None and PIPELINE_MODE=real.
    text_blocks : SI text-block dicts already produced by the MERMaid branch.
                  When provided, used directly without re-reading from disk.
    """
    if settings.PIPELINE_MODE == "mock":
        return _load_mock(paper_id, source="si")
    else:
        return _parse_real(paper_id, text_path, source="si", text_blocks=text_blocks)


def load_cde_result(result_path: Path) -> dict:
    """Load a previously saved CDE output JSON from disk."""
    return load_json(result_path)


# ── Mock mode ─────────────────────────────────────────────────────────────────

def _load_mock(paper_id: str, source: str) -> dict:
    """Return the bundled sample CDE output with the paper_id patched in."""
    logger.info(f"[mock] Loading sample CDE output for {paper_id} ({source})")
    data = load_json(settings.SAMPLE_CDE_OUTPUT)
    data["paper_id"] = paper_id

    out_path = settings.CDE_OUTPUT_DIR / f"{paper_id}_cde_{source}.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    save_json(data, out_path)
    logger.info(f"[mock] CDE output saved → {out_path}")
    return data


# ── Real mode ─────────────────────────────────────────────────────────────────

def _parse_real(
    paper_id: str,
    text_path: Optional[str],
    source: str,
    text_blocks: Optional[list] = None,
) -> dict:
    """
    Parse paper text for chemical mentions.

    Tries ChemDataExtractor2 first (if installed). Falls back to a lightweight
    regex scan of the pdfplumber text blocks passed from the MERMaid branch
    (via *text_blocks*) or loaded from disk if not provided.

    Parameters
    ----------
    text_blocks : Pre-extracted text blocks from the MERMaid branch.  When
                  provided, the fallback uses them directly instead of
                  re-loading from the mermaid JSON on disk.
    """
    try:
        return _parse_with_cde(paper_id, text_path, source, text_blocks=text_blocks)
    except ImportError:
        logger.warning("ChemDataExtractor2 not installed — using lightweight fallback. "
                       "Install with: pip install ChemDataExtractor2")
        return _parse_with_fallback(paper_id, source, text_blocks=text_blocks)


def _parse_with_cde(
    paper_id: str,
    text_path: Optional[str],
    source: str,
    text_blocks: Optional[list] = None,
) -> dict:
    """
    Run ChemDataExtractor2 on the PDF or text file.

    Parameters
    ----------
    text_blocks : Pre-extracted blocks from the MERMaid branch (not used by
                  the full CDE path which reads the file directly, but
                  accepted for a consistent call signature).
    """
    from chemdataextractor import Document  # noqa: PLC0415

    if not text_path or not Path(text_path).exists():
        raise FileNotFoundError(f"No text file for CDE: {text_path}")

    with open(text_path, "rb") as f:
        doc = Document.from_file(f)

    chemical_mentions = [
        {"text": cem.text, "full_name": cem.text, "role_guess": "", "context": ""}
        for cem in doc.cems
    ]

    result = {
        "paper_id":          paper_id,
        "chemical_mentions": chemical_mentions,
        "condition_mentions": [],
        "procedure_blocks":  [],
        "text_chunks":       [],
    }
    _save_and_log(result, paper_id, source)
    return result


def _parse_with_fallback(
    paper_id: str,
    source: str,
    text_blocks: Optional[list] = None,
) -> dict:
    """
    Lightweight chemical-name scan using the pdfplumber text blocks produced
    by the MERMaid branch. Looks for common glycosylation reagents and
    compound labels (e.g. 3a, NIS, TfOH) without requiring CDE.

    Parameters
    ----------
    text_blocks : Text-block dicts passed directly from the MERMaid branch.
                  When provided, they are used as-is so no disk read is needed.
                  When None, falls back to loading from the mermaid JSON on disk.
    """
    import re

    # Use blocks passed from the MERMaid branch when available; otherwise
    # load from the MERMaid JSON file written to disk.
    if text_blocks is None:
        mermaid_json = settings.MERMAID_OUTPUT_DIR / f"{paper_id}_mermaid.json"
        if mermaid_json.exists():
            data = load_json(mermaid_json)
            key = "text_blocks" if source == "main" else "si_blocks"
            text_blocks = data.get(key, [])
        else:
            text_blocks = []

    # Patterns: compound labels like 1a–9z, common glycosylation reagents/solvents
    label_re   = re.compile(r'\b\d{1,2}[a-z]\b')
    reagent_re = re.compile(
        r'\b(NIS|TfOH|DMTST|AgOTf|TMSOTf|BF3|DDQ|CSA|TFA|DCM|MeCN|Et2O|THF|toluene)\b',
        re.IGNORECASE,
    )
    condition_re = re.compile(
        r'(-?\d+\s*°C|\d+\s*(mol\s*%|equiv|h\b|min\b))',
        re.IGNORECASE,
    )

    chemical_mentions: list = []
    condition_mentions: list = []
    seen_chems: set = set()

    for block in text_blocks:
        text = block.get("text", "")
        for m in label_re.findall(text):
            if m not in seen_chems:
                seen_chems.add(m)
                chemical_mentions.append(
                    {"text": m, "full_name": m, "role_guess": "compound_label", "context": text[:120]}
                )
        for m in reagent_re.findall(text):
            key = m.lower()
            if key not in seen_chems:
                seen_chems.add(key)
                chemical_mentions.append(
                    {"text": m, "full_name": m, "role_guess": "reagent", "context": text[:120]}
                )
        for m in condition_re.findall(text):
            val = m[0] if isinstance(m, tuple) else m
            condition_mentions.append({"field": "condition", "value": val, "context": text[:120]})

    logger.info(
        f"[fallback CDE] {paper_id}/{source}: "
        f"{len(chemical_mentions)} chemical mention(s), {len(condition_mentions)} condition(s)"
    )

    result = {
        "paper_id":          paper_id,
        "chemical_mentions": chemical_mentions,
        "condition_mentions": condition_mentions,
        "procedure_blocks":  [],
        "text_chunks":       [{"chunk_id": b["block_id"], "text": b["text"], "section": b.get("section")}
                               for b in text_blocks],
    }
    _save_and_log(result, paper_id, source)
    return result


def _save_and_log(result: dict, paper_id: str, source: str) -> None:
    out_path = settings.CDE_OUTPUT_DIR / f"{paper_id}_cde_{source}.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    save_json(result, out_path)
    logger.info(f"CDE output saved → {out_path}")
