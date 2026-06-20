"""
Completeness Check — Module 5 (Source-Aware Router).

Evaluates the scheme extractions produced by run_figure_extraction() and
classifies missing fields by which downstream module should handle them.

In real mode a GPT-4o call is made with the prompt from
configs/prompts/04_completeness_check.md.  The model returns the
source-aware routing schema:

  {
    "core_complete": bool,
    "core_status": str,          # complete | complete_with_not_reported_fields | missing_core_fields
    "missing_core_fields": [...],
    "fill_target_fields": [...],  # → Module 6 (text fill)

    "si_required": bool,
    "si_target_fields": [...],    # → SI Extraction

    "external_lookup_required": bool,
    "external_target_fields": [...],  # → External lookup (PubChem etc.)

    "not_reported_fields": [...],
    "low_confidence_fields": [...],

    "should_run_text_fill": bool,
    "should_run_si_extraction": bool,
    "should_run_external_lookup": bool,

    # Backward-compat aliases (computed from core_complete)
    "is_complete": bool,          # alias for core_complete
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
    / "04_completeness_check.md"
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
        figure_id                  : str
        core_complete              : bool
        core_status                : str
        missing_core_fields        : list
        fill_target_fields         : list   ← targeted input for Module 6
        si_required                : bool
        si_target_fields           : list
        external_lookup_required   : bool
        external_target_fields     : list
        not_reported_fields        : list
        low_confidence_fields      : list
        should_run_text_fill       : bool
        should_run_si_extraction   : bool
        should_run_external_lookup : bool
        is_complete                : bool   ← backward-compat alias for core_complete
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

    complete_count = sum(
        1 for r in results
        if r.get("core_complete", r.get("is_complete", False))
    )
    logger.info(
        f"[check_completeness] {complete_count}/{len(results)} scheme(s) core-complete"
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

        # ── Schema normalisation ──────────────────────────────────────────────
        if "core_complete" in result:
            # New schema: just ensure the backward-compat alias is present.
            result.setdefault("is_complete", result["core_complete"])
            result.setdefault("extraction_failed",
                result.get("core_status") == "extraction_failed")
        elif "is_complete" in result:
            # Old-style LLM response — promote every field to the new schema so
            # downstream code never has to handle two different shapes.
            old_is_complete = result["is_complete"]
            result.setdefault("core_complete", old_is_complete)
            result.setdefault("core_status",
                "complete" if old_is_complete else "missing_core_fields")

            # Derive fill_target_fields from whichever old list exists
            raw_need_filling = result.get(
                "fields_need_filling",
                result.get("missing_or_uncertain_fields", []),
            )
            fill_fields = []
            for item in (raw_need_filling if isinstance(raw_need_filling, list) else []):
                if isinstance(item, str):
                    fill_fields.append(item)
                elif isinstance(item, dict) and item.get("field"):
                    fill_fields.append(item["field"])

            result.setdefault("missing_core_fields", fill_fields)
            result.setdefault("fill_target_fields",  fill_fields)
            result.setdefault("si_required",          False)
            result.setdefault("si_target_fields",     [])
            result.setdefault("external_lookup_required", False)
            result.setdefault("external_target_fields",   [])
            result.setdefault("not_reported_fields",  [])
            result.setdefault("low_confidence_fields", [])
            result.setdefault("should_run_text_fill",  bool(fill_fields))
            result.setdefault("should_run_si_extraction",   False)
            result.setdefault("should_run_external_lookup", False)
            result.setdefault("extraction_failed",    False)

        logger.debug(
            f"[check_completeness] {figure_id}: "
            f"core_complete={result.get('core_complete')}, "
            f"status={result.get('core_status')}, "
            f"fill_targets={result.get('fill_target_fields', [])}"
        )
        return result

    except Exception as exc:
        logger.warning(f"[check_completeness] LLM call failed for {figure_id}: {exc}")
        return _check_rule_based(scheme, figure_id)


def _check_rule_based(scheme: dict, figure_id: str) -> dict:
    """
    Rule-based completeness check used in mock mode or as LLM fallback.
    Produces the full source-aware routing schema.
    """
    step_analysis = scheme.get("step_analysis", {})
    steps         = step_analysis.get("reaction_steps", [])
    paths         = scheme.get("reaction_paths", [])

    # ── Quarantine: no reaction steps means Module 3 extraction failed ─────────
    # Do not route to fill or SI — there is nothing to fill into.
    # Use failure_code + has_image from Module 3's result to split into two
    # diagnostic buckets so Engineering knows where to look.
    if not steps:
        failure_code = scheme.get("failure_code", "unknown")
        has_image    = scheme.get("has_image", True)   # default True = assume image existed

        # Three-bucket failure_source split:
        #
        # module_3_technical        → API / infra issue; fix key, image path, or rate limit.
        #                             The LLM never got a real chance to run.
        #
        # module_3_response_format  → LLM ran on a readable image but returned broken/
        #                             unparseable JSON.  This is a Module 3 output-size or
        #                             prompt issue, NOT evidence the figure was wrong.
        #                             Large schemes (16+ steps) often hit this.
        #
        # possible_module_4_false_positive → LLM ran, image was present, JSON was valid,
        #                             but no reaction_steps were returned.  The figure is
        #                             likely not a reaction scheme; Module 4 should have
        #                             filtered it out.
        if failure_code in ("api_error", "rate_limit", "timeout",
                            "no_api_key", "unexpected_error"):
            failure_source = "module_3_technical"
            failure_source_note = f"API-level failure ({failure_code}) — LLM never ran."
        elif not has_image:
            failure_source = "module_3_technical"
            failure_source_note = "Image file was missing or unreadable on disk."
        elif failure_code == "malformed_response":
            failure_source = "module_3_response_format"
            failure_source_note = (
                "LLM returned a response but JSON was invalid or unparseable. "
                "Likely cause: response truncated (large scheme) or prompt output-format "
                "issue. Check: scheme_steps_count vs max_tokens limit."
            )
        elif failure_code in ("empty_result", "unknown"):
            failure_source = "possible_module_4_false_positive"
            failure_source_note = (
                "LLM ran on a readable image but returned no reaction steps. "
                "Figure may not be a reaction scheme — check whether Module 4 "
                "should have filtered this figure out."
            )
        else:
            failure_source = "unknown"
            failure_source_note = f"Unclassified (failure_code={failure_code})."

        return {
            "core_complete":       False,
            "is_complete":         False,
            "core_status":         "extraction_failed",
            "extraction_failed":   True,
            "failure_source":      failure_source,
            "failure_source_note": failure_source_note,
            "failure_code":        failure_code,
            "quarantine_reason": (
                f"No reaction_steps returned by Module 3. "
                f"failure_source={failure_source}: {failure_source_note}"
            ),
            "missing_core_fields":      ["reaction_steps"],
            "fill_target_fields":       [],
            "si_required":              False,
            "si_target_fields":         [],
            "external_lookup_required": False,
            "external_target_fields":   [],
            "not_reported_fields":      [],
            "low_confidence_fields":    [],
            "should_run_text_fill":        False,
            "should_run_si_extraction":    False,
            "should_run_external_lookup":  False,
        }

    missing_core:    list = []
    fill_targets:    list = []
    not_reported:    list = []
    low_confidence:  list = []

    # Phase: unknown → low_confidence, not a core blocker
    phase = step_analysis.get("phase")
    if not phase or phase == "unknown":
        low_confidence.append("phase")

    # Reaction paths: genuinely required for multi-step schemes
    if not paths and any(s.get("step", 0) > 1 for s in steps):
        missing_core.append("reaction_paths")
        fill_targets.append("reaction_paths")

    # Per-step checks for glycosylation steps
    for step in steps:
        if step.get("reaction_type") != "glycosylation":
            continue
        step_num = step.get("step", "?")
        for field in ("donor", "acceptor", "product"):
            val = step.get(field)
            if not val:
                key = f"step_{step_num}_{field}_id"
                missing_core.append(key)
                fill_targets.append(key)

        # Conditions check
        conditions = step.get("conditions", step.get("reaction_conditions", {}))
        if isinstance(conditions, dict):
            if not conditions.get("activator") and not conditions.get("promoter"):
                missing_core.append(f"step_{step_num}_activator")
                fill_targets.append(f"step_{step_num}_activator")
            if not conditions.get("solvent"):
                missing_core.append(f"step_{step_num}_solvent")
                fill_targets.append(f"step_{step_num}_solvent")
            # Yield: not a core blocker — goes to not_reported
            if not conditions.get("yield") and not conditions.get("yield_percent"):
                not_reported.append(f"step_{step_num}_yield_percent")

    # SI fields: always route there, never block core
    si_targets = [
        "donor_mass_mg", "donor_mmol",
        "acceptor_mass_mg", "acceptor_mmol",
        "product_mass_mg",
    ]

    # External lookup fields
    external_targets = ["donor_smiles", "acceptor_smiles", "product_smiles"]

    core_complete = len(missing_core) == 0
    if core_complete:
        core_status = (
            "complete_with_not_reported_fields" if not_reported else "complete"
        )
    else:
        core_status = "missing_core_fields"

    return {
        "core_complete":   core_complete,
        "is_complete":     core_complete,           # backward-compat alias
        "core_status":     core_status,
        "missing_core_fields":  missing_core,
        "fill_target_fields":   fill_targets,

        "si_required":          True,
        "si_target_fields":     si_targets,

        "external_lookup_required": True,
        "external_target_fields":   external_targets,

        "not_reported_fields":  not_reported,
        "low_confidence_fields": low_confidence,

        "should_run_text_fill":        bool(fill_targets),
        "should_run_si_extraction":    True,
        "should_run_external_lookup":  True,
    }


def log_completeness_summary(results: List[dict]) -> dict:
    """
    Log a structured per-run breakdown of completeness routing decisions
    and return the counters dict so callers can inspect or persist it.

    Example log lines:
        [completeness_summary] 16 scheme(s) — core_complete=13 |
            text_fill_needed=2 | si_needed=14 | external_lookup_needed=16 |
            extraction_failed=1 | not_reported_yield=5 | phase_low_confidence=16
        [completeness_summary] extraction_failed breakdown —
            module_3_technical=0 | possible_module_4_false_positive=1
    """
    n = len(results)
    counters = {
        "core_complete_count":          sum(1 for r in results if r.get("core_complete", False)),
        "text_fill_needed_count":       sum(1 for r in results if r.get("should_run_text_fill", False)),
        "si_needed_count":              sum(1 for r in results if r.get("should_run_si_extraction", False)),
        "external_lookup_needed_count": sum(1 for r in results if r.get("should_run_external_lookup", False)),
        "extraction_failed_count":      sum(1 for r in results if r.get("extraction_failed", False)),
        "not_reported_yield_count":     sum(
            1 for r in results
            if any("yield" in f for f in r.get("not_reported_fields", []))
        ),
        "phase_low_confidence_count":   sum(
            1 for r in results
            if "phase" in r.get("low_confidence_fields", [])
        ),
    }
    summary_parts = " | ".join(
        f"{k.replace('_count', '')}={v}" for k, v in counters.items()
    )
    logger.info(f"[completeness_summary] {n} scheme(s) — {summary_parts}")

    # Extra line: break down extraction_failed by failure_source
    if counters["extraction_failed_count"] > 0:
        source_breakdown: dict = {}
        for r in results:
            if r.get("extraction_failed"):
                src = r.get("failure_source", "unknown")
                source_breakdown[src] = source_breakdown.get(src, 0) + 1
        src_parts = " | ".join(f"{k}={v}" for k, v in sorted(source_breakdown.items()))
        logger.info(f"[completeness_summary] extraction_failed breakdown — {src_parts}")
        counters["failure_source_breakdown"] = source_breakdown

    return counters


def log_fill_targets_summary(completeness_reports: List[dict]) -> dict:
    """
    Aggregate fill_target_fields across all incomplete schemes into a frequency
    table and log it.  Shows which fields Module 3 is most consistently missing,
    which distinguishes a prompt gap from random figure-quality variability.

    Interpretation:
        same fields missing repeatedly  → Module 3 prompt not emphasising those fields
        random fields missing           → figure image / caption quality variability

    Example log line:
        [fill_targets_summary] step_1_activator=6 | step_1_solvent=5 |
            step_1_donor_id=2 | step_2_acceptor_id=1
    """
    freq: dict = {}
    for r in completeness_reports:
        if not r.get("core_complete", False) and not r.get("extraction_failed", False):
            for field in r.get("fill_target_fields", []):
                freq[field] = freq.get(field, 0) + 1

    if not freq:
        logger.info(
            "[fill_targets_summary] No text-fill targets — "
            "all schemes are core-complete or quarantined"
        )
        return {}

    sorted_freq = dict(sorted(freq.items(), key=lambda x: x[1], reverse=True))
    summary = " | ".join(f"{k}={v}" for k, v in sorted_freq.items())
    logger.info(f"[fill_targets_summary] {summary}")
    return sorted_freq


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
