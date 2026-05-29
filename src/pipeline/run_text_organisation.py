"""
Branch A — Text Organisation: CDE extraction + Agent AI chunk classification.

In real mode a single GPT-4o call receives all main-article and SI text and
returns a structured JSON that partitions it into the six evidence categories
defined in configs/prompts/02_01_text_organization.md.

In mock mode the CDE adapter output is used directly with rule-based source
mapping (no LLM call) for test stability.
"""

import json
from pathlib import Path

from configs import settings
from src.adapters.chemdataextractor_adapter import parse_main_text, parse_si_text
from src.utils.logging_utils import get_logger

logger = get_logger(__name__)

_PROMPT_PATH = Path(__file__).parents[2] / "configs" / "prompts" / "02_01_text_organization.md"

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

    Parameters
    ----------
    documents : Output of load_documents() — must contain paper_id,
                text_blocks, and si_blocks.

    Returns
    -------
    dict with keys:
        paper_id, synthesis_procedures, general_procedures,
        compound_characterization, figure_captions, tables,
        chemical_mentions, condition_mentions,
        text_chunks, si_chunks, procedure_blocks,
        text_organisation  (full LLM output in real mode, empty dict in mock)
    """
    paper_id    = documents["paper_id"]
    text_blocks = documents.get("text_blocks", [])
    si_blocks   = documents.get("si_blocks", [])

    logger.info(f"[run_text_organisation] Branch A starting for {paper_id}")

    # ── Step 1: CDE extraction ─────────────────────────────────────────────────
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

    chemical_mentions  = (
        main_cde.get("chemical_mentions", [])
        + si_cde.get("chemical_mentions", [])
    )
    condition_mentions = (
        main_cde.get("condition_mentions", [])
        + si_cde.get("condition_mentions", [])
    )

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

    # ── Step 2: Agent AI (real mode) — batch classification ───────────────────
    text_organisation: dict = {}
    if settings.PIPELINE_MODE == "real":
        main_text = "\n\n".join(b.get("text", b) if isinstance(b, dict) else str(b)
                                for b in text_blocks)
        si_text   = "\n\n".join(b.get("text", b) if isinstance(b, dict) else str(b)
                                for b in si_blocks)
        text_organisation = _classify_with_llm(main_text, si_text, paper_id)
    else:
        logger.info(f"[run_text_organisation] mock mode — skipping LLM classification")

    # ── Build category buckets ─────────────────────────────────────────────────
    # Real mode: populate buckets from LLM JSON output.
    # Mock mode: use CDE source_type mapping.
    buckets: dict = {cat: [] for cat in CHUNK_CATEGORIES}

    if text_organisation:
        org = text_organisation.get("text_organisation", {})
        buckets["synthesis_procedure"] = org.get("synthesis_procedures", [])
        buckets["general_procedure"]   = org.get("general_procedures", [])
        buckets["compound_characterization"] = org.get("compound_characterization", [])
        buckets["figure_caption"]      = org.get("figure_captions", [])
        buckets["table"]               = org.get("tables", [])
        buckets["irrelevant"]          = org.get("irrelevant_text", [])
    else:
        all_chunks = text_chunks + si_chunks
        for chunk in all_chunks:
            cat    = chunk.get("source_type", "main_text")
            mapped = _map_source_type(cat)
            if mapped in buckets:
                buckets[mapped].append(chunk)

    logger.info(
        f"[run_text_organisation] Branch A complete for {paper_id}: "
        f"synthesis_procedures={len(buckets['synthesis_procedure'])}, "
        f"general_procedures={len(buckets['general_procedure'])}, "
        f"compound_characterization={len(buckets['compound_characterization'])}"
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
        "text_organisation":         text_organisation,
    }


# ── Internal helpers ──────────────────────────────────────────────────────────

def _classify_with_llm(main_text: str, si_text: str, paper_id: str) -> dict:
    """
    One GPT-4o call that classifies all text according to Module 2.01 prompt.
    Returns the parsed JSON dict (keys: text_organisation, organisation_summary).
    Falls back to empty dict on failure.
    """
    if not settings.OPENAI_API_KEY:
        logger.warning("[run_text_organisation] OPENAI_API_KEY not set — skipping LLM")
        return {}

    system_prompt = _load_system_prompt()
    if not system_prompt:
        return {}

    # Truncate to stay under token limits (128 k context window).
    main_excerpt = main_text[:40_000]
    si_excerpt   = si_text[:40_000]

    user_content = (
        f"Main Article text:\n{main_excerpt}\n\n"
        f"Supporting Information text:\n{si_excerpt}"
    )

    try:
        from openai import OpenAI
        client = OpenAI(api_key=settings.OPENAI_API_KEY)
        resp = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user",   "content": user_content},
            ],
            response_format={"type": "json_object"},
            max_tokens=8192,
        )
        raw = resp.choices[0].message.content
        result = json.loads(raw)
        summary = result.get("organisation_summary", {})
        logger.info(
            f"[run_text_organisation] LLM classification complete for {paper_id}: "
            f"synthesis_procedures={'synthesis_procedures_found' in str(summary)}"
        )
        return result

    except Exception as exc:
        logger.warning(f"[run_text_organisation] LLM call failed for {paper_id}: {exc}")
        return {}


def _load_system_prompt() -> str:
    """Extract the prompt text block from the Module 2.01 markdown file."""
    try:
        md = _PROMPT_PATH.read_text(encoding="utf-8")
        # The prompt lives between the first ```text fence and its closing ```.
        start = md.find("```text\n")
        if start == -1:
            start = md.find("```\n")
        end   = md.find("\n```", start + 4)
        if start != -1 and end != -1:
            return md[start + md[start:].find("\n") + 1 : end].strip()
        # Fallback: return entire markdown as the system message.
        return md.strip()
    except Exception as exc:
        logger.warning(f"[run_text_organisation] Could not load prompt file: {exc}")
        return ""


def _map_source_type(source_type: str) -> str:
    mapping = {
        "procedure": "synthesis_procedure",
        "main_text": "general_procedure",
        "si_text":   "general_procedure",
        "caption":   "figure_caption",
        "table":     "table",
    }
    return mapping.get(source_type, "general_procedure")


def _prefix_ids(items: list, prefix: str) -> list:
    for item in items:
        for key in ("block_id", "chunk_id"):
            if key in item:
                item[key] = prefix + item[key]
    return items
