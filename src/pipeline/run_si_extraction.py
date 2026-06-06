"""
SI Experimental Extraction — Module 2.04.

Reads the Supporting Information (SI) experimental section and extracts
masses, mmol, volumes, SMILES, and other quantities for each product
compound that appears in the extracted reaction schemes.

How it works
------------
Chemistry SI files have one paragraph per compound, like:

    "Compound 24. Donor 11 (48 mg, 0.12 mmol) and acceptor 21 (35 mg,
     0.10 mmol) were dissolved in dry DCM (2 mL). NIS (54 mg, 0.24 mmol)
     and TfOH (2 µL, 0.023 mmol) were added at −40 °C... Yield: 78%."

We send GPT-4o the full SI text plus the list of product IDs we care about.
It returns a dict: { "24": { donor_mass_mg, donor_mmol, ... }, ... }

The result is then merged into the CSV rows in save_outputs.py — any
field that was null from figure extraction gets filled from the SI data.

Architecture position
---------------------
Called after run_figure_extraction() and before save_outputs().
Requires si_blocks (already loaded by load_documents via the Shared Input Layer).
Skipped silently if no SI text is available.
"""

import json
from pathlib import Path
from typing import List, Optional

from configs import settings
from src.utils.logging_utils import get_logger

logger = get_logger(__name__)

_PROMPT_PATH = (
    Path(__file__).parents[2]
    / "configs" / "prompts"
    / "02_04_si_experimental.md"
)


def run_si_extraction(
    documents: dict,
    scheme_extractions: List[dict],
) -> dict:
    """
    Extract experimental quantities from the SI for all product compounds
    found in scheme_extractions.

    Parameters
    ----------
    documents         : Output of load_documents() — must contain si_blocks.
    scheme_extractions: Output of run_figure_extraction() — list of scheme dicts.

    Returns
    -------
    dict mapping product_id (str) → experimental data dict with fields:
        donor_id, donor_mass_mg, donor_mmol, donor_smiles,
        acceptor_id, acceptor_mass_mg, acceptor_mmol, acceptor_smiles,
        activator_1_name, activator_1_mass_mg, activator_1_mmol,
        activator_2_name, activator_2_volume_uL, activator_2_mmol,
        solvent_name, solvent_volume_mL,
        temperature_initial_celsius, temperature_final_celsius,
        reaction_time_min, product_mass_mg,
        yield_percent, a_b_ratio, product_smiles, comments

    Returns empty dict if no SI text available or extraction fails.
    """
    paper_id = documents.get("paper_id", "unknown")

    # ── Gather SI text ────────────────────────────────────────────────────────
    si_blocks = documents.get("si_blocks", [])
    si_text   = "\n\n".join(
        b.get("text", b) if isinstance(b, dict) else str(b)
        for b in si_blocks
    ).strip()

    if not si_text:
        logger.info(
            f"[run_si_extraction] No SI text for {paper_id} — skipping. "
            f"To enable, add si_path to the paper config and make sure the SI PDF exists."
        )
        return {}

    # ── Collect product IDs from scheme extractions ───────────────────────────
    product_ids = _collect_product_ids(scheme_extractions)
    if not product_ids:
        logger.info(f"[run_si_extraction] No product IDs found in schemes — skipping")
        return {}

    logger.info(
        f"[run_si_extraction] Extracting SI data for {len(product_ids)} "
        f"product(s): {sorted(product_ids)[:10]}{'...' if len(product_ids) > 10 else ''}"
    )

    # ── Mock mode ─────────────────────────────────────────────────────────────
    if settings.PIPELINE_MODE != "real":
        logger.info(f"[run_si_extraction] mock mode — returning empty SI data")
        return {}

    # ── Real mode: GPT-4o call ────────────────────────────────────────────────
    if not settings.OPENAI_API_KEY:
        logger.warning("[run_si_extraction] OPENAI_API_KEY not set — skipping")
        return {}

    return _extract_with_llm(si_text, product_ids, paper_id)


# ── Internal helpers ──────────────────────────────────────────────────────────

def _collect_product_ids(scheme_extractions: List[dict]) -> set:
    """Walk scheme_extractions and collect all product compound IDs."""
    ids = set()
    for scheme in scheme_extractions:
        steps = scheme.get("step_analysis", {}).get("reaction_steps", [])
        for step in steps:
            prod = step.get("product")
            if isinstance(prod, dict):
                cid = prod.get("compound_id") or prod.get("id")
            elif isinstance(prod, str):
                cid = prod
            else:
                cid = None
            if cid and str(cid).strip():
                ids.add(str(cid).strip())
    return ids


def _load_prompt_template() -> str:
    """Load the prompt template from the markdown file."""
    try:
        md    = _PROMPT_PATH.read_text(encoding="utf-8")
        start = md.find("```text\n")
        if start == -1:
            start = md.find("```\n")
        end = md.find("\n```", start + 4)
        if start != -1 and end != -1:
            return md[start + md[start:].find("\n") + 1 : end].strip()
        return md.strip()
    except Exception as exc:
        logger.warning(f"[run_si_extraction] Could not load prompt: {exc}")
        return ""


def _chunk_by_paragraph(text: str, max_chars: int = 60_000) -> list:
    """
    Split SI text at paragraph boundaries (blank lines) so that a single
    compound's procedure paragraph is never split across two chunks.

    Each chunk is at most max_chars long. If a single paragraph exceeds
    max_chars (very rare), it is included as its own oversized chunk rather
    than being silently dropped.
    """
    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]

    chunks = []
    current = []
    current_len = 0

    for para in paragraphs:
        para_len = len(para) + 2  # +2 for the "\n\n" separator we'll rejoin with
        if current_len + para_len > max_chars and current:
            # Flush current chunk before adding this paragraph
            chunks.append("\n\n".join(current))
            current = []
            current_len = 0
        current.append(para)
        current_len += para_len

    if current:
        chunks.append("\n\n".join(current))

    return chunks


def _extract_with_llm(si_text: str, product_ids: set, paper_id: str) -> dict:
    """
    Send SI text + product ID list to GPT-4o and parse the result.

    Strategy:
    - Split SI into 60k-char chunks (safe for context window)
    - Send each chunk independently; failures per chunk are skipped, not fatal
    - Within each chunk, ask for at most 10 compound IDs to keep responses short
    - Use max_tokens=8192 to avoid truncated JSON
    """
    prompt_template = _load_prompt_template()
    if not prompt_template:
        return {}

    CHUNK_SIZE   = 60_000   # max chars per chunk (safety cap)
    BATCH_SIZE   = 10       # compound IDs per request (keeps JSON response manageable)
    MAX_TOKENS   = 8192     # enough for ~10 compounds with full data

    chunks = _chunk_by_paragraph(si_text, max_chars=CHUNK_SIZE)
    id_list = sorted(product_ids)
    id_batches = [id_list[i:i + BATCH_SIZE] for i in range(0, len(id_list), BATCH_SIZE)]

    logger.info(
        f"[run_si_extraction] SI text {len(si_text)} chars → "
        f"{len(chunks)} chunk(s) × {len(id_batches)} ID batch(es) "
        f"= {len(chunks) * len(id_batches)} total calls"
    )

    merged: dict = {}

    try:
        from openai import OpenAI
        client = OpenAI(api_key=settings.OPENAI_API_KEY)

        for chunk_idx, chunk in enumerate(chunks):
            for batch_idx, id_batch in enumerate(id_batches):
                ids_str = ", ".join(id_batch)
                system_prompt = prompt_template.replace("{PRODUCT_IDS}", ids_str)

                user_content = (
                    f"SI Text (part {chunk_idx + 1} of {len(chunks)}):\n\n{chunk}\n\n"
                    "Return a JSON object mapping each found product_id to its "
                    "experimental data. Only include compounds whose synthesis "
                    "paragraph you can find in this text chunk. Return only JSON."
                )

                try:
                    import time
                    time.sleep(5)   # 5s between calls keeps us under 30k TPM limit
                    resp = client.chat.completions.create(
                        model="gpt-4o",
                        messages=[
                            {"role": "system", "content": system_prompt},
                            {"role": "user",   "content": user_content},
                        ],
                        response_format={"type": "json_object"},
                        max_tokens=MAX_TOKENS,
                    )
                    raw    = resp.choices[0].message.content
                    result = json.loads(raw)

                    # Merge: later chunks fill nulls, don't overwrite found data
                    for cid, data in result.items():
                        if not isinstance(data, dict):
                            continue
                        if cid not in merged:
                            merged[cid] = data
                        else:
                            for k, v in data.items():
                                if v is not None and merged[cid].get(k) is None:
                                    merged[cid][k] = v

                    found_this = [c for c in id_batch if c in result and
                                  any(v is not None for v in result[c].values())]
                    if found_this:
                        logger.info(
                            f"[run_si_extraction] chunk {chunk_idx+1}, "
                            f"batch {batch_idx+1}: found {found_this}"
                        )

                except Exception as chunk_exc:
                    logger.warning(
                        f"[run_si_extraction] chunk {chunk_idx+1} batch {batch_idx+1} "
                        f"failed: {chunk_exc} — skipping"
                    )
                    continue

        found = [cid for cid, d in merged.items()
                 if any(v is not None for v in d.values())]
        logger.info(
            f"[run_si_extraction] SI extraction complete for {paper_id}: "
            f"{len(found)}/{len(product_ids)} product(s) found in SI"
        )
        return merged

    except Exception as exc:
        logger.warning(f"[run_si_extraction] SI extraction failed for {paper_id}: {exc}")
        return {}
