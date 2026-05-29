"""
Post-processing & Provenance — Module 7.

Two entry points:

post_process_and_save()  ← NEW primary path
    Takes the scheme fill_results (from fill_scheme_missing_fields()) and runs
    a final GPT-4o standardization pass using the prompt from
    configs/prompts/06_Post-processing & Provenance.md.
    Saves: final scheme JSON, intermediate files, provenance summary.

save_outputs()  ← legacy path (kept for backward compatibility)
    Takes the flat ReactionRecord and saves it as before.

Saved files per paper:
  data/outputs/{paper_id}_schemes.json          ← NEW primary output
  data/outputs/{paper_id}_provenance.json       ← NEW provenance summary
  data/outputs/{paper_id}_final.json            ← legacy record output
  data/intermediate/{paper_id}_merged.json
  data/intermediate/{paper_id}_unresolved_ids.json
  data/intermediate/{paper_id}_report.json
"""

import json
from pathlib import Path
from typing import Optional, List

from configs import settings
from src.models.reaction_record import ReactionRecord
from src.utils.json_utils import save_json
from src.utils.logging_utils import get_logger

logger = get_logger(__name__)

_PROMPT_PATH = (
    Path(__file__).parents[2]
    / "configs" / "prompts"
    / "06_Post-processing & Provenance.md"
)


# ── NEW primary path ──────────────────────────────────────────────────────────

def post_process_and_save(
    paper_id: str,
    fill_results: List[dict],
    scheme_extractions: List[dict],
    completeness_reports: List[dict],
    unified: dict,
    id_dict: dict,
    output_dir: Optional[Path] = None,
    intermediate_dir: Optional[Path] = None,
) -> dict:
    """
    Run Module 7 post-processing on each filled scheme, then save all outputs.

    Parameters
    ----------
    paper_id             : Paper identifier.
    fill_results         : Output of fill_scheme_missing_fields() — one per scheme.
    scheme_extractions   : Output of run_figure_extraction().
    completeness_reports : Output of check_completeness().
    unified              : Merged extraction dict (for intermediate save).
    id_dict              : Identifier dictionary (for unresolved save).
    output_dir           : Where to save final outputs.
    intermediate_dir     : Where to save debug files.

    Returns
    -------
    dict mapping output_name → str(path)
    """
    output_dir       = Path(output_dir       or settings.OUTPUT_DIR)
    intermediate_dir = Path(intermediate_dir or settings.INTERMEDIATE_DIR)
    output_dir.mkdir(parents=True, exist_ok=True)
    intermediate_dir.mkdir(parents=True, exist_ok=True)

    prompt_text = _load_prompt()
    paths       = {}

    # ── Post-process each scheme ───────────────────────────────────────────────
    final_schemes = []
    provenance_summaries = []

    for fill_result in fill_results:
        figure_id = fill_result.get("figure_id", "unknown")
        logger.info(f"[post_process_and_save] Post-processing {figure_id} …")

        if settings.PIPELINE_MODE == "real" and prompt_text:
            pp_result = _postprocess_with_llm(fill_result, prompt_text, figure_id)
        else:
            pp_result = _postprocess_rule_based(fill_result, figure_id)

        final_schemes.append({
            "figure_id":        figure_id,
            "final_output":     pp_result.get("final_output", {}),
            "unresolved_items": pp_result.get("unresolved_items", []),
        })
        provenance_summaries.append({
            "figure_id":        figure_id,
            "provenance_summary": pp_result.get("provenance_summary", {}),
        })

    # ── Save outputs ───────────────────────────────────────────────────────────

    # 1. Final scheme extraction (primary output)
    schemes_path = output_dir / f"{paper_id}_schemes.json"
    save_json({"paper_id": paper_id, "schemes": final_schemes}, schemes_path)
    paths["final_schemes"] = str(schemes_path)

    # 2. Provenance summary
    prov_path = output_dir / f"{paper_id}_provenance.json"
    save_json({"paper_id": paper_id, "provenance": provenance_summaries}, prov_path)
    paths["provenance"] = str(prov_path)

    # 3. Intermediate merged extraction
    merged_path = intermediate_dir / f"{paper_id}_merged.json"
    save_json(unified, merged_path)
    paths["merged_extraction"] = str(merged_path)

    # 4. Unresolved identifiers
    unresolved_path = intermediate_dir / f"{paper_id}_unresolved_ids.json"
    save_json(id_dict.get("unresolved", {}), unresolved_path)
    paths["unresolved_ids"] = str(unresolved_path)

    # 5. Completeness reports
    comp_path = intermediate_dir / f"{paper_id}_completeness.json"
    save_json(completeness_reports, comp_path)
    paths["completeness_reports"] = str(comp_path)

    logger.info(f"Saved all outputs for {paper_id}:")
    for name, path in paths.items():
        logger.info(f"  {name}: {path}")

    return paths


# ── Internal helpers (new path) ───────────────────────────────────────────────

def _postprocess_with_llm(fill_result: dict, prompt_text: str, figure_id: str) -> dict:
    """One GPT-4o call for Module 7 standardization + provenance."""
    if not settings.OPENAI_API_KEY:
        return _postprocess_rule_based(fill_result, figure_id)

    user_content = (
        f"Filled reaction extraction JSON:\n"
        f"{json.dumps(fill_result, indent=2)}"
    )

    try:
        from openai import OpenAI
        client = OpenAI(api_key=settings.OPENAI_API_KEY)
        resp = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": prompt_text},
                {"role": "user",   "content": user_content},
            ],
            response_format={"type": "json_object"},
            max_tokens=4096,
        )
        raw    = resp.choices[0].message.content
        result = json.loads(raw)
        logger.info(f"[post_process_and_save] Post-processing complete for {figure_id}")
        return result

    except Exception as exc:
        logger.warning(f"[post_process_and_save] LLM call failed for {figure_id}: {exc}")
        return _postprocess_rule_based(fill_result, figure_id)


def _postprocess_rule_based(fill_result: dict, figure_id: str) -> dict:
    """
    Rule-based post-processing: standardize reaction_type and phase labels,
    set null for missing values, build provenance summary.
    """
    VALID_REACTION_TYPES = {
        "glycosylation", "protection", "deprotection",
        "global_deprotection", "other", "unknown",
    }
    VALID_PHASES = {"solution", "solid", "mixed", "unknown"}

    filled = fill_result.get("filled_output", {})
    steps  = filled.get("reaction_steps", [])

    # Standardize phase.
    phase = filled.get("phase", "unknown")
    if phase not in VALID_PHASES:
        phase = "unknown"

    clean_steps = []
    for step in steps:
        step = dict(step)
        rt = step.get("reaction_type", "unknown")
        if rt not in VALID_REACTION_TYPES:
            step["reaction_type"] = "unknown"
        clean_steps.append(step)

    final_output = {
        "phase":             phase,
        "scheme_steps_count": len(clean_steps),
        "reaction_steps":    clean_steps,
    }

    # Simple provenance summary.
    has_conditions = any(
        s.get("solution_conditions") or s.get("solid_conditions")
        for s in clean_steps
        if s.get("reaction_type") == "glycosylation"
    )
    provenance_summary = {
        "figure_used":              True,
        "main_text_used":           False,
        "SI_used":                  False,
        "compound_dictionary_used": False,
        "manual_check_required":    bool(fill_result.get("unfilled_fields")),
    }

    unresolved = fill_result.get("unfilled_fields", [])

    return {
        "final_output":     final_output,
        "provenance_summary": provenance_summary,
        "unresolved_items": unresolved,
    }


def _load_prompt() -> str:
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
        logger.warning(f"[post_process_and_save] Could not load prompt: {exc}")
        return ""


# ── Legacy path (ReactionRecord) ─────────────────────────────────────────────

def save_outputs(
    record: ReactionRecord,
    unified: dict,
    id_dict: dict,
    output_dir: Optional[Path] = None,
    intermediate_dir: Optional[Path] = None,
) -> dict:
    """
    Legacy: save flat ReactionRecord outputs.
    Kept for backward compatibility.
    """
    output_dir       = Path(output_dir       or settings.OUTPUT_DIR)
    intermediate_dir = Path(intermediate_dir or settings.INTERMEDIATE_DIR)
    output_dir.mkdir(parents=True, exist_ok=True)
    intermediate_dir.mkdir(parents=True, exist_ok=True)
    paper_id = record.paper_id
    paths    = {}

    final_path = output_dir / f"{paper_id}_final.json"
    save_json(record.to_dict(), final_path)
    paths["final_record"] = str(final_path)

    merged_path = intermediate_dir / f"{paper_id}_merged.json"
    save_json(unified, merged_path)
    paths["merged_extraction"] = str(merged_path)

    unresolved_path = intermediate_dir / f"{paper_id}_unresolved_ids.json"
    save_json(id_dict.get("unresolved", {}), unresolved_path)
    paths["unresolved_ids"] = str(unresolved_path)

    report = {
        "paper_id":           paper_id,
        "completeness_score": record.completeness_score,
        "unresolved_fields":  record.unresolved_fields,
        "provenance":         record.provenance,
    }
    report_path = intermediate_dir / f"{paper_id}_report.json"
    save_json(report, report_path)
    paths["report"] = str(report_path)

    logger.info(f"Saved outputs for {paper_id}:")
    for name, path in paths.items():
        logger.info(f"  {name}: {path}")

    return paths
