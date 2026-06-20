"""
Adapter for MERMaid — the multimodal PDF/figure/table extraction pipeline.

Modes
-----
mock : Load pre-built sample JSON from data/samples/. No external tool needed.
real : Run VisualHeist (figure extraction) + DataRaider (GPT-4o extraction).
       Set PIPELINE_MODE=real and OPENAI_API_KEY in your .env file.

How real mode works
-------------------
Step 1  VisualHeist reads the PDF page-by-page and saves every figure/table
        it finds as a PNG image in data/mermaid_outputs/<paper_id>_images/.

Step 2  DataRaider sends each PNG to GPT-4o, which reads the image and fills
        in a structured JSON with glycosylation-specific fields
        (Donor, Acceptor, Promoter, Solvent, Temperature, Time, Yield, …).
        JSON files are saved to data/mermaid_outputs/<paper_id>_dataraider/.

Step 3  text_blocks and si_blocks are now provided by the Shared Input Layer
        (load_documents.py) via the optional *documents* parameter, so that
        pdfplumber extraction is performed exactly once per run.  If *documents*
        is not provided, text_blocks / si_blocks default to empty lists.

Step 4  Everything is combined into our unified internal format and returned.
"""

import json
import shutil
import tempfile
from pathlib import Path
from typing import Optional

from configs import settings
from src.utils.json_utils import load_json, save_json
from src.utils.logging_utils import get_logger

logger = get_logger(__name__)

# Glycosylation-specific fields DataRaider will try to extract from each figure.
GLYCO_KEYS = [
    "Entry",
    "Donor",
    "Acceptor",
    "Product",
    "Promoter",
    "Solvent",
    "Temperature",
    "Time",
    "Yield",
    "Stereochemistry",
    "Procedure",
    "Notes",
]


# ── Public API ────────────────────────────────────────────────────────────────

def run_mermaid_on_paper(
    paper_id: str,
    pdf_path: str,
    si_path: Optional[str] = None,
    output_dir: Optional[Path] = None,
    documents: Optional[dict] = None,
) -> dict:
    """
    Run MERMaid on a single paper and return its extraction output as a dict.

    Parameters
    ----------
    paper_id  : Unique paper identifier used to name output files.
    pdf_path  : Path to the main paper PDF.
    si_path   : Optional path to the supplementary information PDF.
    output_dir: Directory for MERMaid outputs (defaults to settings.MERMAID_OUTPUT_DIR).
    documents : Optional output of load_documents() from the Shared Input Layer.
                When provided, text_blocks and si_blocks are taken from here
                instead of being extracted again by pdfplumber.

    Returns
    -------
    dict with keys: paper_id, source_pdf, figures, tables, text_blocks, si_blocks
    """
    output_dir = Path(output_dir or settings.MERMAID_OUTPUT_DIR)
    output_dir.mkdir(parents=True, exist_ok=True)

    if settings.PIPELINE_MODE == "mock":
        return _run_mock(paper_id, output_dir)
    else:
        return _run_real(paper_id, pdf_path, si_path, output_dir, documents=documents)


def load_mermaid_result(result_path: Path) -> dict:
    """Load a previously saved MERMaid output JSON from disk."""
    return load_json(result_path)


# ── Mock mode ─────────────────────────────────────────────────────────────────

def _run_mock(paper_id: str, output_dir: Path) -> dict:
    """Load the bundled sample MERMaid output and patch in the current paper_id."""
    logger.info(f"[mock] Loading sample MERMaid output for {paper_id}")
    data = load_json(settings.SAMPLE_MERMAID_OUTPUT)
    data["paper_id"] = paper_id

    out_path = output_dir / f"{paper_id}_mermaid.json"
    save_json(data, out_path)
    logger.info(f"[mock] Saved → {out_path}")
    return data


# ── Real mode ─────────────────────────────────────────────────────────────────

def _run_real(
    paper_id: str,
    pdf_path: str,
    si_path: Optional[str],
    output_dir: Path,
    documents: Optional[dict] = None,
) -> dict:
    """
    Full MERMaid pipeline using VisualHeist + DataRaider.

    1. VisualHeist extracts every figure/table from the PDF as PNG images.
    2. DataRaider (GPT-4o) reads those images and produces structured JSON
       with glycosylation-specific fields.
    3. text_blocks and si_blocks come from the Shared Input Layer (documents).
       If not provided, they default to empty lists.
    4. Everything is combined into our internal format and saved to disk.
    """
    if not settings.OPENAI_API_KEY:
        raise ValueError(
            "OPENAI_API_KEY is not set. Add it to your .env file to use real mode."
        )

    image_dir    = output_dir / f"{paper_id}_images"
    json_dir     = output_dir / f"{paper_id}_dataraider"
    prompt_dir   = settings.MERMAID_PROMPTS_DIR
    image_dir.mkdir(parents=True, exist_ok=True)
    json_dir.mkdir(parents=True, exist_ok=True)

    # ── Step 1: VisualHeist ───────────────────────────────────────────────────
    existing_pngs = list(image_dir.glob("*.png"))
    if existing_pngs:
        logger.info(f"VisualHeist images already exist ({len(existing_pngs)} PNGs) — skipping extraction")
        figures = _build_figures_from_existing_images(image_dir)
    else:
        figures = _run_visualheist(paper_id, pdf_path, image_dir)
    logger.info(f"VisualHeist: {len(figures)} figure(s) for {paper_id}")

    # ── Step 2: DataRaider ────────────────────────────────────────────────────
    # If DataRaider JSON outputs already exist from a previous run, load them
    # directly — this lets the pipeline proceed even when the dataraider package
    # is not installed in the current environment.
    existing_jsons = list(json_dir.glob("*.json"))
    if existing_jsons:
        logger.info(
            f"DataRaider outputs already exist ({len(existing_jsons)} JSON files) "
            f"— skipping DataRaider run and loading from cache"
        )
        tables = _load_dataraider_cache(json_dir)
    else:
        tables = _run_dataraider(paper_id, image_dir, json_dir, prompt_dir)
    logger.info(f"DataRaider extracted {len(tables)} reaction table(s) from {paper_id}")

    # ── Step 3: Use text_blocks from the Shared Input Layer ───────────────────
    # The Shared Input Layer (load_documents.py) extracted pdfplumber blocks
    # once already. Reuse them here to avoid double-extraction.
    if documents is not None:
        text_blocks = documents.get("text_blocks", [])
        si_blocks   = documents.get("si_blocks", [])
        logger.info(
            f"Using shared input layer text blocks: "
            f"{len(text_blocks)} main, {len(si_blocks)} SI"
        )
    else:
        # Fallback: no documents provided — default to empty.
        text_blocks = []
        si_blocks   = []
        logger.warning(
            f"No documents dict provided to _run_real for {paper_id}; "
            f"text_blocks will be empty. Pass documents=load_documents(paper) "
            f"from the shared input layer."
        )

    # ── Step 4: Assemble and save ─────────────────────────────────────────────
    result = {
        "paper_id":    paper_id,
        "source_pdf":  str(pdf_path),
        "figures":     figures,
        "tables":      tables,
        "text_blocks": text_blocks,
        "si_blocks":   si_blocks,
    }

    out_path = output_dir / f"{paper_id}_mermaid.json"
    save_json(result, out_path)
    logger.info(f"MERMaid result saved → {out_path}")
    return result


# ── Step 1 helper: VisualHeist ────────────────────────────────────────────────

def _build_figures_from_existing_images(image_dir: Path) -> list:
    """
    Build figure dicts from PNGs that VisualHeist already saved on a prior run.
    DataRaider moves images into relevant_images/ and irrelevant_images/ subdirs,
    so we search all subfolders to find every PNG.
    """
    # Prefer relevant_images/ first, then root, then irrelevant_images/
    png_files = (
        sorted((image_dir / "relevant_images").glob("*.png"))
        + sorted(image_dir.glob("*.png"))
        + sorted((image_dir / "irrelevant_images").glob("*.png"))
    )
    # Deduplicate while preserving order
    seen = set()
    unique_pngs = []
    for p in png_files:
        if p not in seen:
            seen.add(p)
            unique_pngs.append(p)

    figures = []
    for i, png in enumerate(unique_pngs):
        figures.append({
            "figure_id": f"FIG_{i+1:02d}",
            "page": 0,
            "caption": "",
            "image_path": str(png),
            "text_labels": [],
            "bounding_box": None,
            "is_relevant": False,
            "relevance_confidence": 0.0,
            "relevance_reasons": [],
        })
    return figures


def _run_visualheist(paper_id: str, pdf_path: str, image_dir: Path) -> list:
    """
    Run VisualHeist on a single PDF.
    Creates a temporary directory containing only this PDF, runs VisualHeist,
    then collects the output PNG paths.

    Returns a list of figure dicts matching our internal Figure format.
    """
    from visualheist.methods_visualheist import batch_pdf_to_figures_and_tables

    # VisualHeist processes a directory of PDFs, not individual files.
    with tempfile.TemporaryDirectory() as tmp_pdf_dir:
        pdf_dest = Path(tmp_pdf_dir) / Path(pdf_path).name
        shutil.copy(pdf_path, pdf_dest)

        logger.info(f"VisualHeist: processing {Path(pdf_path).name} …")
        batch_pdf_to_figures_and_tables(
            input_dir   = tmp_pdf_dir,
            output_dir  = str(image_dir),
            large_model = False,     # set True for higher accuracy (slower + more RAM)
        )

    # Collect all output PNGs and build figure dicts.
    figures = []
    png_files = sorted(image_dir.glob("*.png"))
    for i, png in enumerate(png_files):
        figures.append({
            "figure_id":         f"FIG_{i+1:02d}",
            "page":              _guess_page_from_filename(png.name),
            "caption":           "",    # VisualHeist saves images only; captions come from pdfplumber
            "image_path":        str(png),
            "text_labels":       [],
            "bounding_box":      None,
            "is_relevant":       False,
            "relevance_confidence": 0.0,
            "relevance_reasons": [],
        })
    return figures


# ── Step 2 helper: DataRaider ─────────────────────────────────────────────────

def _load_dataraider_cache(json_dir: Path) -> list:
    """Load existing DataRaider JSON outputs without re-running DataRaider."""
    tables = []
    for json_file in sorted(json_dir.glob("*.json")):
        try:
            data = load_json(json_file)
            if isinstance(data, list):
                tables.extend(data)
            elif isinstance(data, dict):
                tables.append(data)
        except Exception as exc:
            logger.warning(f"[mermaid_adapter] Could not load {json_file}: {exc}")
    logger.info(f"[mermaid_adapter] Loaded {len(tables)} table(s) from DataRaider cache")
    return tables


def _run_dataraider(
    paper_id: str,
    image_dir: Path,
    json_dir: Path,
    prompt_dir: Path,
) -> list:
    """
    Run DataRaider on extracted images.

    DataRaider:
    1. Filters images — keeps only glycosylation reaction figures/tables.
    2. Checks segmentation quality.
    3. Extracts structured JSON (with GLYCO_KEYS) from each relevant image.
    4. Cleans up temporary files.

    Returns a list of table dicts, each with the extracted reaction rows.
    """
    from dataraider.processor_info import DataRaiderInfo
    from dataraider.reaction_dictionary_formating import construct_initial_prompt
    from dataraider.process_images import batch_process_images, clear_temp_files
    from dataraider.filter_image import filter_images, check_segmentation

    # Use our glycosylation-specific filter prompt if it exists,
    # otherwise fall back to MERMaid's default prompt.
    glyco_filter = settings.PROMPTS_DIR / "mermaid_filter_image.txt"
    if glyco_filter.exists():
        _install_glyco_filter_prompt(glyco_filter, prompt_dir)
        filter_prompt_name = "filter_image_prompt"   # DataRaider reads by name
    else:
        filter_prompt_name = "filter_image_prompt"

    api_key = settings.OPENAI_API_KEY

    # RxnScribe must be given a real checkpoint path — passing None causes a crash.
    # Download it from HuggingFace (cached after first download, ~200 MB).
    logger.info("Downloading RxnScribe checkpoint (cached after first run) …")
    from huggingface_hub import hf_hub_download
    ckpt_path = hf_hub_download("yujieq/RxnScribe", "pix2seq_reaction_full.ckpt")

    logger.info("Initialising DataRaider …")
    info = DataRaiderInfo(api_key=api_key, device="cpu", ckpt_path=ckpt_path)

    logger.info("Building glycosylation extraction prompt …")
    construct_initial_prompt(str(prompt_dir), GLYCO_KEYS, new_run_keys={})

    logger.info("Filtering images for glycosylation content …")
    filter_images(info, str(prompt_dir), filter_prompt_name, str(image_dir))

    # check_segmentation is skipped: VisualHeist crops images without captions,
    # so that step always rejects them as "improperly segmented".
    logger.info("Extracting reaction data from relevant images …")
    batch_process_images(
        info,
        str(image_dir),
        str(prompt_dir),
        "get_data_prompt",
        "update_dict_prompt",
        str(json_dir),
    )

    clear_temp_files(str(prompt_dir), str(image_dir))

    # Collect and return all DataRaider JSON outputs as table dicts.
    return _parse_dataraider_jsons(json_dir)


def _install_glyco_filter_prompt(glyco_filter: Path, prompt_dir: Path) -> None:
    """Copy our glycosylation filter prompt into MERMaid's Prompts directory."""
    dest = prompt_dir / "filter_image_prompt.txt"
    # Backup the original if we haven't already.
    backup = prompt_dir / "filter_image_prompt_original.txt"
    if not backup.exists() and dest.exists():
        shutil.copy(dest, backup)
    shutil.copy(glyco_filter, dest)
    logger.debug(f"Installed glyco filter prompt → {dest}")


# ── Parsing helpers ───────────────────────────────────────────────────────────

def _parse_dataraider_jsons(json_dir: Path) -> list:
    """
    Read all JSON files produced by DataRaider and return them as a list of
    table dicts that our pipeline can consume.

    DataRaider produces two possible top-level shapes:

    Shape A — flat reaction entries (original MERMaid format):
        { "reaction_1": { "Donor": "3a", "Yield": "78%", ... }, "footnotes": {} }

    Shape B — nested "Optimization Runs" (real-mode output observed in practice):
        { "SMILES": { "reactants": "...", "products": "..." },
          "Optimization Runs": { "1": { "Entry": "1", "Temperature": "0°C", ... } } }

    Both shapes are handled. Files where GPT-4o returned a plain-text string
    instead of JSON are skipped with a warning.
    """
    tables = []
    for json_file in sorted(json_dir.glob("*.json")):
        try:
            data = load_json(json_file)
        except Exception as exc:
            logger.warning(f"Could not read DataRaider JSON {json_file}: {exc}")
            continue

        if not isinstance(data, dict):
            logger.warning(
                f"DataRaider JSON {json_file.name} is not a dict "
                f"(got {type(data).__name__}) — GPT-4o likely returned plain text, skipping"
            )
            continue

        rows = []
        footnotes = data.pop("footnotes", {})
        data.pop("SMILES", None)  # SMILES block is not a reaction row

        # Shape B: "Optimization Runs" → { entry_id: { field: value, ... } }
        opt_runs = data.pop("Optimization Runs", None)
        if opt_runs and isinstance(opt_runs, dict):
            for entry_val in opt_runs.values():
                if isinstance(entry_val, dict):
                    rows.append(entry_val)

        # Shape A: remaining top-level dicts are reaction rows
        for entry_val in data.values():
            if isinstance(entry_val, dict):
                rows.append(entry_val)

        if rows:
            tables.append({
                "table_id":  json_file.stem,
                "page":      None,
                "caption":   "",
                "headers":   GLYCO_KEYS,
                "rows":      rows,
                "footnotes": footnotes,
                "source":    "dataraider",
            })
    return tables


def _guess_page_from_filename(filename: str) -> int:
    """
    VisualHeist names images as '{pdf_stem}_image_{N}.png'.
    We can't recover page numbers from the filename alone, so return 0.
    Page numbers can be enriched later if needed.
    """
    return 0
