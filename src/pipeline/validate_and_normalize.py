"""
Completeness Check — Module 5.

Evaluates the scheme extractions produced by run_figure_extraction() to
determine whether each scheme has enough information for dataset construction.

In real mode a GPT-4o call is made with the prompt from
configs/prompts/04_Completeness Check.md.  The model returns:
  {
    "is_complete": bool,
    "overall_status": str,
    "missing_or_uncertain_fields": [...],
    "fields_ready_for_post_processing": [...],
    "fields_need_filling": [...],
    "manual_check_required": bool
  }

The legacy ReactionRecord.compute_completeness() path is kept for backward
compatibility when scheme_extractions is not available.
"""

import json
from pathlib import Path
from typing import List

from src.models.reaction_record import ReactionRecord, TRACKED_FIELDS
from src.utils.text_utils import normalize_solvent, normalize_temperature
from src.utils.logging_utils import get_logger
from configs import settings

logger = get_logger(__name__)

_PROMPT_PATH = (
    Path(__file__).parents[2]
    / "configs" / "prompts"
    / "04_Completeness Check.md"
)

REQUIRED_FIELDS = ["donor_id", "acceptor_id", "product_id"]


def check_completeness(
    scheme_extractions: List[dict],
    text_org: dict,
    id_dict: dict,
) -> List[dict]:
    """
    Run the Module 5 completeness check on each scheme extraction.

    Parameters
    ----------
    scheme_extractions : Output of run_figure_extraction().
    text_org           : Output of run_text_organisation() (evidence context).
    id_dict            : Output of run_identifier_dictionary().

    Returns
    -------
    List of completeness report dicts, one per scheme.  Each dict has:
        figure_id               : str
        is_complete             : bool
        overall_status          : str
        missing_or_uncertain_fields : list
        fields_ready_for_post_processing : list
        fields_need_filling     : list
        manual_check_required   : bool
    """
    if not scheme_extractions:
        return []

    prompt_text = _load_prompt()
    results = []

    for scheme in scheme_extractions:
        figure_id = scheme.get("figure_id", "unknown")
        logger.info(f"[check_completeness] Checking {figure_id} …")

        if settings.PIPELINE_MODE == "real" and prompt_text:
            report = _check_with_llm(scheme, text_org, id_dict, prompt_text, figure_id)
        else:
            report = _check_rule_based(scheme, figure_id)

        report["figure_id"] = figure_id
        results.append(report)

    complete_count = sum(1 for r in results if r.get("is_complete"))
    logger.info(
        f"[check_completeness] {complete_count}/{len(results)} scheme(s) complete"
    )
    return results


def validate_and_normalize(record: ReactionRecord) -> ReactionRecord:
    """
    Legacy path: validate and normalize a flat ReactionRecord.
    Kept for backward compatibility with the old pipeline flow.
    """
    _normalize_fields(record)
    issues = _check_required_record(record) + _check_plausibility(record)
    for issue in issues:
        logger.warning(f"Validation issue [{record.paper_id}]: {issue}")

    record.compute_completeness()
    logger.info(
        f"Completeness: {record.completeness_score:.0%} | "
        f"Unresolved: {record.unresolved_fields}"
    )
    return record


# ── Internal helpers ──────────────────────────────────────────────────────────

def _check_with_llm(
    scheme: dict,
    text_org: dict,
    id_dict: dict,
    prompt_text: str,
    figure_id: str,
) -> dict:
    """
    One GPT-4o call for the Module 5 completeness check.
    Falls back to rule-based check on failure.
    """
    if not settings.OPENAI_API_KEY:
        return _check_rule_based(scheme, figure_id)

    # Build context: the extraction JSON + summary of available evidence.
    scheme_json = json.dumps({
        "reaction_paths": scheme.get("reaction_paths", []),
        "step_analysis":  scheme.get("step_analysis", {}),
    }, indent=2)

    evidence_summary = _build_evidence_summary(text_org, id_dict)

    user_content = (
        f"Extracted scheme JSON:\n{scheme_json}\n\n"
        f"Available evidence summary:\n{evidence_summary}"
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
            max_tokens=1024,
        )
        raw    = resp.choices[0].message.content
        result = json.loads(raw)
        logger.debug(
            f"[check_completeness] {figure_id}: "
            f"is_complete={result.get('is_complete')}, "
            f"status={result.get('overall_status')}"
        )
        return result

    except Exception as exc:
        logger.warning(f"[check_completeness] LLM call failed for {figure_id}: {exc}")
        return _check_rule_based(scheme, figure_id)


def _check_rule_based(scheme: dict, figure_id: str) -> dict:
    """Rule-based completeness check used in mock mode or as fallback."""
    step_analysis = scheme.get("step_analysis", {})
    steps         = step_analysis.get("reaction_steps", [])
    paths         = scheme.get("reaction_paths", [])

    missing: list  = []
    ready:   list  = []

    if not step_analysis.get("phase"):
        missing.append({"level": "scheme", "field": "phase", "status": "missing",
                        "reason": "Phase not determined.", "recommended_source_to_check": "figure"})
    else:
        ready.append("phase")

    if not paths:
        missing.append({"level": "scheme", "field": "reaction_paths", "status": "missing",
                        "reason": "No reaction paths extracted.", "recommended_source_to_check": "figure"})
    else:
        ready.append("reaction_paths")

    for step in steps:
        if step.get("reaction_type") == "glycosylation":
            for field in ("donor", "acceptor", "product"):
                val = step.get(field)
                if not val:
                    missing.append({
                        "level":  "step",
                        "step":    step.get("step"),
                        "field":   field,
                        "status": "missing",
                        "reason": f"Glycosylation step {step.get('step')} missing {field}.",
                        "recommended_source_to_check": "figure_and_text",
                    })
                else:
                    if field not in ready:
                        ready.append(field)

    is_complete = len(missing) == 0
    return {
        "is_complete":                      is_complete,
        "overall_status":                   "complete" if is_complete else "partially_complete",
        "missing_or_uncertain_fields":      missing,
        "fields_ready_for_post_processing": ready,
        "fields_need_filling":              [m["field"] for m in missing],
        "manual_check_required":            False,
    }


def _build_evidence_summary(text_org: dict, id_dict: dict) -> str:
    parts = []
    n_syn = len(text_org.get("synthesis_procedures", []))
    n_gen = len(text_org.get("general_procedures", []))
    n_cap = len(text_org.get("figure_captions", []))
    parts.append(
        f"Text organisation: {n_syn} synthesis_procedures, "
        f"{n_gen} general_procedures, {n_cap} figure_captions"
    )
    n_res   = len(id_dict.get("resolved", {}))
    n_unres = len(id_dict.get("unresolved", {}))
    parts.append(f"Compound dictionary: {n_res} verified, {n_unres} unresolved")
    return "\n".join(parts)


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
        logger.warning(f"[check_completeness] Could not load prompt: {exc}")
        return ""


# ── Legacy helpers (ReactionRecord path) ─────────────────────────────────────

def _normalize_fields(record: ReactionRecord) -> None:
    if record.solvent not in ("NR", ""):
        record.solvent = normalize_solvent(record.solvent)
    if record.temperature not in ("NR", ""):
        record.temperature = normalize_temperature(record.temperature)


def _check_required_record(record: ReactionRecord) -> List[str]:
    issues = []
    for field in REQUIRED_FIELDS:
        val = getattr(record, field, "NR")
        if val == "NR" or not val:
            issues.append(f"Required field '{field}' is NR")
    return issues


def _check_plausibility(record: ReactionRecord) -> List[str]:
    import re
    issues = []
    checks = [
        ("yield_",       r'\d+%$',   "yield does not look like a percentage"),
        ("temperature",  r'\d|room', "temperature value looks unusual"),
    ]
    for attr, pattern, message in checks:
        val = getattr(record, attr, "NR")
        if val and val != "NR":
            if not re.search(pattern, val, re.IGNORECASE):
                issues.append(f"Field '{attr}' value '{val}': {message}")
    return issues
