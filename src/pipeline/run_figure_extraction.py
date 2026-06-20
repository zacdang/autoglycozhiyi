"""
Primary Figure-based Extraction — Module 3.

For each relevant synthesis figure, sends the PNG image + a TXT description
(caption + nearby text) to GPT-4o vision with the two-instruction-set prompt
from configs/prompts/03_Primary Figure-based Extraction.md.

Each call returns:
  {
    "reaction_paths": [ { "path": "11 + 42 -> 43 -> 44 -> 15" }, ... ],
    "step_analysis": {
      "phase": "solution | solid",
      "scheme_steps_count": <int>,
      "reaction_steps": [ { "step": 1, "reaction_type": "glycosylation",
                             "donor": "...", "acceptor": "...",
                             "product": "...", "solution_conditions": {...} }, ... ],
      "notes": "..."
    }
  }

In mock mode returns a minimal placeholder structure so downstream modules
have well-typed inputs without making any API calls.
"""

import base64
import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import List, Optional

from configs import settings
from src.utils.logging_utils import get_logger

logger = get_logger(__name__)

_PROMPT_PATH = (
    Path(__file__).parents[2]
    / "configs" / "prompts"
    / "03_Primary Figure-based Extraction.md"
)


def run_figure_extraction(
    relevant_figures: List[dict],
    text_org: dict,
    id_dict: dict,
) -> List[dict]:
    """
    Run primary figure-based extraction on every relevant figure.

    Parameters
    ----------
    relevant_figures : Output of classify_relevant_figures() — list of figure dicts
                       sorted by relevance_confidence descending.
    text_org         : Output of run_text_organisation() — used to build TXT
                       description context for each figure.
    id_dict          : Output of run_identifier_dictionary() — compound name
                       context passed into the TXT description.

    Returns
    -------
    List of scheme extraction dicts, one per relevant figure.  Each dict has:
        figure_id       : str
        image_path      : str
        reaction_paths  : list of { "path": str }
        step_analysis   : { phase, scheme_steps_count, reaction_steps, notes }
        raw_llm_output  : dict (full LLM response for debugging)
    """
    if not relevant_figures:
        logger.info("[run_figure_extraction] No relevant figures — skipping")
        return []

    if settings.PIPELINE_MODE != "real":
        return _mock_extractions(relevant_figures)

    prompt_text = _load_prompt()
    if not prompt_text:
        logger.warning("[run_figure_extraction] Could not load prompt — returning empty")
        return []

    # Build a richer Module 2 → Module 3 identifier context for the TXT prompt.
    identifier_context = _build_identifier_context(id_dict)

    # ── Parallel extraction: up to 2 concurrent GPT-4o vision calls ──────────
    # max_workers=2 is intentional — GPT-4o image calls are ~4 k tokens each;
    # two in parallel stays safely under the 30 k TPM rate limit.
    MAX_WORKERS = 2

    # Pre-build all work items so the executor closure captures no loop variables.
    work_items = []
    for fig in relevant_figures:
        figure_id   = fig.get("figure_id", "unknown")
        image_path  = fig.get("image_path", "")
        txt_context = _build_txt_context(fig, text_org, identifier_context)
        work_items.append((fig, figure_id, image_path, txt_context))

    results_map: dict = {}   # figure_id → result dict (insertion order preserved after)

    def _extract_worker(work_item):
        fig, fid, img_path, txt_ctx = work_item
        logger.info(f"[run_figure_extraction] Extracting scheme from {fid} …")
        extraction = _extract_one_figure(fid, img_path, txt_ctx, prompt_text)
        return fid, {
            "figure_id":      fid,
            "image_path":     img_path,
            "reaction_paths": extraction.get("reaction_paths", []),
            "step_analysis":  extraction.get("step_analysis", {}),
            "raw_llm_output": extraction,
        }

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        future_to_fid = {executor.submit(_extract_worker, item): item[1]
                         for item in work_items}
        for future in as_completed(future_to_fid):
            fid = future_to_fid[future]
            try:
                fid_result, result_dict = future.result()
                results_map[fid_result] = result_dict
            except Exception as exc:
                logger.warning(f"[run_figure_extraction] Worker for {fid} raised: {exc}")
                results_map[fid] = {
                    "figure_id":      fid,
                    "image_path":     "",
                    "reaction_paths": [],
                    "step_analysis":  {},
                    "raw_llm_output": {},
                }

    # Restore original figure order.
    results = [results_map[item[1]] for item in work_items if item[1] in results_map]

    logger.info(
        f"[run_figure_extraction] Extracted {len(results)} scheme(s) from "
        f"{len(relevant_figures)} relevant figure(s) (parallel workers={MAX_WORKERS})"
    )
    return results


# ── Internal helpers ──────────────────────────────────────────────────────────

def _extract_one_figure(
    figure_id: str,
    image_path: str,
    txt_context: str,
    prompt_text: str,
) -> dict:
    """
    One GPT-4o vision call for a single figure.
    Returns the parsed JSON dict (reaction_paths + step_analysis).
    Falls back to an empty structure on failure.
    """
    if not settings.OPENAI_API_KEY:
        logger.warning(f"[run_figure_extraction] OPENAI_API_KEY not set — skipping {figure_id}")
        return {}

    image_b64 = _encode_image(image_path)

    # Build the user message content.
    content: list = [{"type": "text", "text": prompt_text}]
    if image_b64:
        content.append({
            "type": "image_url",
            "image_url": {
                "url":    f"data:image/png;base64,{image_b64}",
                "detail": "high",
            },
        })
    else:
        logger.warning(f"[run_figure_extraction] No image for {figure_id} — text-only call")

    if txt_context:
        content.append({
            "type": "text",
            "text": f"\n\nReaction description file (TXT):\n{txt_context}",
        })

    try:
        from openai import OpenAI
        client = OpenAI(api_key=settings.OPENAI_API_KEY)
        resp = client.chat.completions.create(
            model="gpt-4o",
            messages=[{"role": "user", "content": content}],
            response_format={"type": "json_object"},
            max_tokens=4096,
        )
        finish_reason = resp.choices[0].finish_reason
        raw = resp.choices[0].message.content

        if raw is None:
            logger.warning(
                f"[run_figure_extraction] {figure_id}: GPT-4o returned None content "
                f"(finish_reason={finish_reason}). Retrying without json_object mode."
            )
            return _extract_one_figure_plaintext(figure_id, content)

        if finish_reason == "length":
            logger.warning(
                f"[run_figure_extraction] {figure_id}: response truncated (max_tokens). "
                f"Attempting to parse partial JSON."
            )

        result = json.loads(raw)

        steps = result.get("step_analysis", {}).get("scheme_steps_count", 0)
        paths = len(result.get("reaction_paths", []))
        logger.info(
            f"[run_figure_extraction] {figure_id}: "
            f"{steps} step(s), {paths} reaction path(s)"
        )
        return result

    except Exception as exc:
        logger.warning(f"[run_figure_extraction] LLM call failed for {figure_id}: {exc}")
        return {}


def _extract_one_figure_plaintext(figure_id: str, content: list) -> dict:
    """
    Fallback when json_object mode returns None.
    Ask GPT-4o to return plain text, then wrap result in minimal structure.
    """
    try:
        from openai import OpenAI
        from configs import settings
        client = OpenAI(api_key=settings.OPENAI_API_KEY)

        fallback_instruction = (
            "Return a JSON object with keys 'reaction_paths' and 'step_analysis'. "
            "reaction_paths is a list of {path: string}. "
            "step_analysis has keys: phase (solution or solid), scheme_steps_count (int), "
            "reaction_steps (list of steps with donor, acceptor, product compound IDs "
            "and solution_conditions), notes (string)."
        )
        # Replace the first text item with the fallback instruction appended
        new_content = list(content)
        if new_content and new_content[0].get("type") == "text":
            new_content[0] = {
                "type": "text",
                "text": new_content[0]["text"] + "\n\n" + fallback_instruction,
            }

        resp = client.chat.completions.create(
            model="gpt-4o",
            messages=[{"role": "user", "content": new_content}],
            max_tokens=8192,
        )
        raw = resp.choices[0].message.content or ""
        # Extract JSON block if wrapped in markdown
        if "```json" in raw:
            raw = raw.split("```json")[1].split("```")[0].strip()
        elif "```" in raw:
            raw = raw.split("```")[1].split("```")[0].strip()
        result = json.loads(raw)
        logger.info(f"[run_figure_extraction] {figure_id}: plaintext fallback succeeded")
        return result
    except Exception as exc:
        logger.warning(f"[run_figure_extraction] {figure_id}: plaintext fallback also failed: {exc}")
        return {}


def _build_txt_context(fig: dict, text_org: dict, identifier_context: str) -> str:
    """
    Build a short TXT description for the figure, combining:
    - figure caption
    - text labels
    - any synthesis_procedures or figure_captions from text_org that mention
      the figure's ID
    - Module 2 identifier dictionary context for compound label resolution
    """
    parts: list = []

    caption = fig.get("caption", "").strip()
    if caption:
        parts.append(f"Caption: {caption}")

    labels = fig.get("text_labels", [])
    if labels:
        parts.append("Labels: " + ", ".join(labels))

    fig_id = fig.get("figure_id", "")
    for block in text_org.get("figure_captions", []):
        ev = block.get("evidence_text", block.get("text", ""))
        label = block.get("label", "")
        if ev and (fig_id in ev or (label and fig_id in label)):
            parts.append(f"Figure caption block: {ev[:500]}")
            break

    if identifier_context:
        parts.append(identifier_context)

    return "\n\n".join(parts)


def _build_identifier_context(id_dict: dict, max_entries: int = 50) -> str:
    """
    Build the Module 2 → Module 3 identifier dictionary context.

    Module 2 produces a resolved identifier dictionary. This helper converts
    that structured output into a compact text block that Module 3 can use
    while reading the primary figure. It keeps the compound ID, resolved name,
    source information, confidence, and evidence text when available.
    """
    resolved = id_dict.get("resolved", {})
    if not resolved:
        return ""

    lines = []
    for idx, (compound_id, entry) in enumerate(resolved.items()):
        if idx >= max_entries:
            remaining = len(resolved) - max_entries
            if remaining > 0:
                lines.append(f"- ... {remaining} additional identifier(s) omitted for brevity")
            break

        compound_name = (
            entry.get("compound_name")
            or entry.get("possible_name")
            or entry.get("name")
            or "NR"
        )
        source = entry.get("source_type") or entry.get("source") or "unknown"
        confidence = entry.get("confidence", "unknown")
        evidence = entry.get("evidence_text") or entry.get("source_text") or ""

        evidence = str(evidence).replace("\n", " ").strip()
        if len(evidence) > 200:
            evidence = evidence[:200] + "..."

        lines.append(
            f"- {compound_id}: {compound_name} | source: {source} | "
            f"confidence: {confidence} | evidence: {evidence}"
        )

    return "Module 2 identifier dictionary for Module 3:\n" + "\n".join(lines)


def _encode_image(image_path: str) -> str:
    if not image_path:
        return ""
    try:
        return base64.b64encode(Path(image_path).read_bytes()).decode("utf-8")
    except Exception:
        return ""


def _load_prompt() -> str:
    """Extract the prompt text block from the Module 4 markdown file."""
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
        logger.warning(f"[run_figure_extraction] Could not load prompt: {exc}")
        return ""


def _mock_extractions(relevant_figures: List[dict]) -> List[dict]:
    """Return placeholder extraction dicts in mock mode."""
    results = []
    for fig in relevant_figures:
        results.append({
            "figure_id":  fig.get("figure_id", "unknown"),
            "image_path": fig.get("image_path", ""),
            "reaction_paths": [{"path": "mock_donor + mock_acceptor -> mock_product"}],
            "step_analysis": {
                "phase":             "solution",
                "scheme_steps_count": 1,
                "reaction_steps": [
                    {
                        "step":          1,
                        "reaction_type": "glycosylation",
                        "donor":         "mock_donor",
                        "acceptor":      "mock_acceptor",
                        "product":       "mock_product",
                        "solution_conditions": {
                            "donor_smiles":              None,
                            "donor_mass_mg":             None,
                            "donor_mmol":                None,
                            "acceptor_smiles":           None,
                            "acceptor_mass_mg":          None,
                            "acceptor_mmol":             None,
                            "equivalents":               None,
                            "activator_1_name":          "NIS",
                            "activator_1_mass_mg":       None,
                            "activator_1_mmol":          None,
                            "activator_2_name":          "TfOH",
                            "activator_2_volume_uL":     None,
                            "activator_2_mmol":          None,
                            "solvent_name":              "DCM",
                            "solvent_volume_mL":         None,
                            "temperature_initial_celsius": "-40",
                            "temperature_final_celsius":   "-40",
                            "reaction_time_min":         "120",
                            "product_mass_mg":           None,
                            "a_b_ratio":                 None,
                            "yield_percent":             "80%",
                            "comments":                  None,
                        },
                    }
                ],
                "notes": "mock mode placeholder",
            },
            "raw_llm_output": {},
        })
    logger.info(f"[run_figure_extraction] mock — {len(results)} placeholder extraction(s)")
    return results
