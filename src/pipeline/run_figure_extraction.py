"""
Primary Figure-based Extraction — Module 4.

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

    # Build a flat compound name lookup for the TXT context.
    name_lookup = _build_name_lookup(id_dict)

    results = []
    for fig in relevant_figures:
        figure_id  = fig.get("figure_id", "unknown")
        image_path = fig.get("image_path", "")
        logger.info(f"[run_figure_extraction] Extracting scheme from {figure_id} …")

        txt_context = _build_txt_context(fig, text_org, name_lookup)
        extraction  = _extract_one_figure(figure_id, image_path, txt_context, prompt_text)

        results.append({
            "figure_id":      figure_id,
            "image_path":     image_path,
            "reaction_paths": extraction.get("reaction_paths", []),
            "step_analysis":  extraction.get("step_analysis", {}),
            "raw_llm_output": extraction,
        })

    logger.info(
        f"[run_figure_extraction] Extracted {len(results)} scheme(s) from "
        f"{len(relevant_figures)} relevant figure(s)"
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
        raw    = resp.choices[0].message.content
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


def _build_txt_context(fig: dict, text_org: dict, name_lookup: dict) -> str:
    """
    Build a short TXT description for the figure, combining:
    - figure caption
    - text labels
    - any synthesis_procedures or figure_captions from text_org that mention
      the figure's ID
    - compound name lookups
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

    if name_lookup:
        pairs = [f"{k}: {v}" for k, v in list(name_lookup.items())[:20]]
        parts.append("Compound name dictionary:\n" + "\n".join(pairs))

    return "\n\n".join(parts)


def _build_name_lookup(id_dict: dict) -> dict:
    """Return { compound_id: compound_name } for all resolved entries."""
    lookup = {}
    for cid, entry in id_dict.get("resolved", {}).items():
        name = entry.get("compound_name") or entry.get("possible_name")
        if name:
            lookup[cid] = name
    return lookup


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
                            "solvent":              "DCM",
                            "temperature":          "-40 °C",
                            "time":                 "2 h",
                            "promoter_or_activator": "NIS/TfOH",
                            "other_reagents":        None,
                            "equivalents":           None,
                            "yield":                "80%",
                            "stereoselectivity":    "alpha",
                        },
                    }
                ],
                "notes": "mock mode placeholder",
            },
            "raw_llm_output": {},
        })
    logger.info(f"[run_figure_extraction] mock — {len(results)} placeholder extraction(s)")
    return results
