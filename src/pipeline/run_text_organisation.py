"""
Branch A — Text Organisation: CDE extraction + Agent AI chunk classification.

This module is one of three parallel branches that run after the shared input
layer. It combines ChemDataExtractor (CDE) chemistry-aware parsing with an
Agent AI classifier that categorises each text chunk by its function in the
paper (synthesis procedure, compound characterisation, figure caption, etc.).

Architecture position
---------------------
Shared Input Layer
→ Branch A: Text Organisation [CDE primary + Agent AI chunk classifier]

Tool assignment
---------------
Step 1 — CDE: extracts chemical_mentions, condition_mentions, and raw text chunks
Step 2 — Agent AI (real mode only): classifies each chunk into a semantic category
          mock mode: all chunks labelled "main_text" (unchanged, for test stability)
"""

from configs import settings
from src.adapters.chemdataextractor_adapter import parse_main_text, parse_si_text
from src.models.paper import Paper
from src.utils.logging_utils import get_logger

logger = get_logger(__name__)

# Allowed chunk classification labels
CHUNK_CATEGORIES = [
    "synthesis_procedure",
    "general_procedure",
    "compound_characterization",
    "figure_caption",
    "table",
    "irrelevant",
]


def run_text_organisation(documents: dict) -> dict:
    """
    Branch A: CDE extraction + Agent AI chunk classification.

    Step 1: Run CDE on documents["text_blocks"] and documents["si_blocks"].
    Step 2: Agent AI classifies each chunk into a semantic category.
            In mock mode: all chunks keep their existing source_type label.
            In real mode: each chunk is sent to GPT-4o for classification.

    Parameters
    ----------
    documents : Output of load_documents() — must contain paper_id,
                text_blocks, and si_blocks.

    Returns
    -------
    dict with keys:
        paper_id                  : str
        synthesis_procedures      : list of chunk dicts
        general_procedures        : list of chunk dicts
        compound_characterization : list of chunk dicts
        figure_captions           : list of chunk dicts
        tables                    : list of chunk dicts
        chemical_mentions         : list (from CDE)
        condition_mentions        : list (from CDE)
        text_chunks               : list — ALL main-text chunks (backward compat)
        si_chunks                 : list — ALL SI chunks (backward compat)
        procedure_blocks          : list — procedure chunks for backward compat
    """
    paper_id    = documents["paper_id"]
    text_blocks = documents.get("text_blocks", [])
    si_blocks   = documents.get("si_blocks", [])

    logger.info(f"[run_text_organisation] Branch A starting for {paper_id}")

    # ── Step 1: CDE extraction ─────────────────────────────────────────────────
    # Pass pre-extracted text_blocks directly to the CDE adapter so it does not
    # re-read from disk.  In mock mode the adapter returns sample data.
    main_cde = parse_main_text(
        paper_id    = paper_id,
        text_path   = documents.get("pdf_path"),
        text_blocks = text_blocks if text_blocks else None,
    )
    si_cde = parse_si_text(
        paper_id    = paper_id,
        text_path   = documents.get("si_path"),
        text_blocks = si_blocks if si_blocks else None,
    )

    # Merge CDE chemical/condition mentions from main + SI.
    chemical_mentions  = (
        main_cde.get("chemical_mentions", [])
        + si_cde.get("chemical_mentions", [])
    )
    condition_mentions = (
        main_cde.get("condition_mentions", [])
        + si_cde.get("condition_mentions", [])
    )

    # Build unified chunk lists, giving SI chunks a "si_" prefix on chunk_id.
    text_chunks: list = list(main_cde.get("text_chunks", []))
    si_chunks:   list = _prefix_ids(list(si_cde.get("text_chunks", [])), "si_")
    procedure_blocks: list = (
        list(main_cde.get("procedure_blocks", []))
        + _prefix_ids(list(si_cde.get("procedure_blocks", [])), "si_")
    )

    logger.info(
        f"[run_text_organisation] CDE: {len(chemical_mentions)} chemical mention(s), "
        f"{len(condition_mentions)} condition mention(s), "
        f"{len(text_chunks)} text chunk(s), {len(si_chunks)} SI chunk(s)"
    )

    # ── Step 2: Agent AI chunk classification ──────────────────────────────────
    all_chunks = text_chunks + si_chunks
    if settings.PIPELINE_MODE == "real":
        all_chunks = _classify_chunks_with_llm(all_chunks)
    # In mock mode: source_type is already set correctly by the CDE adapter.

    # Partition chunks into category buckets.
    buckets: dict = {cat: [] for cat in CHUNK_CATEGORIES}
    for chunk in all_chunks:
        cat = chunk.get("source_type", "main_text")
        # Map CDE source types to canonical categories.
        mapped = _map_source_type(cat)
        if mapped in buckets:
            buckets[mapped].append(chunk)

    logger.info(
        f"[run_text_organisation] Branch A complete for {paper_id}: "
        f"synthesis_procedures={len(buckets['synthesis_procedure'])}, "
        f"general_procedures={len(buckets['general_procedure'])}"
    )

    return {
        "paper_id":                  paper_id,
        "synthesis_procedures":      buckets["synthesis_procedure"],
        "general_procedures":        buckets["general_procedure"],
        "compound_characterization": buckets["compound_characterization"],
        "figure_captions":           buckets["figure_caption"],
        "tables":                    buckets["table"],
        "chemical_mentions":         chemical_mentions,
        "condition_mentions":        condition_mentions,
        "text_chunks":               text_chunks,
        "si_chunks":                 si_chunks,
        "procedure_blocks":          procedure_blocks,
    }


# ── Internal helpers ──────────────────────────────────────────────────────────

def _map_source_type(source_type: str) -> str:
    """Map a CDE source_type string to one of our canonical CHUNK_CATEGORIES."""
    mapping = {
        "procedure":     "synthesis_procedure",
        "main_text":     "general_procedure",
        "si_text":       "general_procedure",
        "caption":       "figure_caption",
        "table":         "table",
    }
    return mapping.get(source_type, "general_procedure")


def _prefix_ids(items: list, prefix: str) -> list:
    """Add a prefix to block_id / chunk_id fields to avoid collisions."""
    for item in items:
        for key in ("block_id", "chunk_id"):
            if key in item:
                item[key] = prefix + item[key]
    return items


def _classify_chunks_with_llm(chunks: list) -> list:
    """
    Real-mode Agent AI chunk classifier.

    Calls GPT-4o for each chunk and sets source_type to the predicted category.
    Only called when PIPELINE_MODE == "real".
    """
    if not settings.OPENAI_API_KEY:
        logger.warning(
            "[run_text_organisation] OPENAI_API_KEY not set — skipping LLM classification"
        )
        return chunks

    try:
        from openai import OpenAI
        import json as _json
        client = OpenAI(api_key=settings.OPENAI_API_KEY)

        categories_str = ", ".join(CHUNK_CATEGORIES)
        classified = []

        for chunk in chunks:
            text = chunk.get("text", "")[:400]
            if not text.strip():
                classified.append(chunk)
                continue

            prompt = (
                f"Classify the following text chunk from a glycosylation chemistry paper "
                f"into exactly one of these categories: {categories_str}.\n"
                f"Reply with a JSON object: {{\"category\": \"<category>\"}}\n\n"
                f"Text:\n{text}"
            )
            try:
                resp = client.chat.completions.create(
                    model="gpt-4o",
                    messages=[{"role": "user", "content": prompt}],
                    response_format={"type": "json_object"},
                    max_tokens=30,
                )
                result = _json.loads(resp.choices[0].message.content)
                cat = result.get("category", "")
                if cat in CHUNK_CATEGORIES:
                    chunk = dict(chunk)
                    chunk["source_type"] = cat
            except Exception as exc:
                logger.debug(f"[run_text_organisation] LLM chunk classification failed: {exc}")

            classified.append(chunk)

        return classified

    except ImportError:
        logger.warning("[run_text_organisation] openai not installed — skipping LLM classification")
        return chunks
