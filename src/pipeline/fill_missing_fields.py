"""
Fill Missing Fields — Module 6.

Two entry points:

fill_scheme_missing_fields()  ← NEW primary path
    Operates on the per-step scheme_extractions from run_figure_extraction().
    For each scheme, a single GPT-4o call fills missing/uncertain fields using
    the evidence hierarchy defined in configs/prompts/05_Fill Missing Fields.md.
    Returns filled_output + unfilled_fields per scheme.

fill_missing_fields()  ← legacy path (kept for backward compatibility)
    Operates on the flat ReactionRecord from the old pipeline.
    Rule-based regex + optional LLM fill.
"""

import json
import re
from pathlib import Path
from typing import Dict, List, Optional

from configs import settings
from src.models.reaction_record import ReactionRecord, TRACKED_FIELDS
from src.utils.text_utils import normalize_solvent, normalize_temperature
from src.utils.logging_utils import get_logger

logger = get_logger(__name__)

_PROMPT_PATH = (
    Path(__file__).parents[2]
    / "configs" / "prompts"
    / "05_Fill Missing Fields.md"
)

# ── Regex patterns for the legacy path ───────────────────────────────────────

PATTERNS: Dict[str, List[str]] = {
    "temperature": [
        r'(-?\d+\s*°C)',
        r'(room\s+temperature|r\.?t\.?)',
    ],
    "time": [
        r'(\d+(?:\.\d+)?\s*h(?:ours?)?)',
        r'(\d+\s+min(?:utes?)?)',
        r'(overnight)',
    ],
    "yield": [
        r'(\d+(?:\.\d+)?\s*%)',
    ],
    "stereochemistry": [
        r'(α/β\s*[>≥<≤]?\s*\d+:\d+)',
        r'(β-anomer|α-anomer)',
        r'\b(alpha|beta)\b',
    ],
    "solvent": [
        r'\bin\s+(CH2Cl2|DCM|THF|Et2O|MeOH|EtOH|MeCN|toluene|benzene|DMSO|DMF)\b',
    ],
    "promoter": [
        r'\b(NIS/TfOH|NIS|TfOH|Tf2O/TTBP|BSI|DMTST|TMSOTf|BF3[·•·]Et2O|AgOTf)\b',
    ],
    "procedure_reference": [
        r'(Procedure\s+[A-Z])',
        r'(see\s+(?:supporting\s+information|SI)(?:,\s*[Ss]ection\s*\d+)?)',
    ],
}


# ── NEW primary path ──────────────────────────────────────────────────────────

def fill_scheme_missing_fields(
    scheme_extractions: List[dict],
    completeness_reports: List[dict],
    text_org: dict,
    id_dict: dict,
) -> List[dict]:
    """
    Fill missing fields in each scheme extraction using Module 6 prompt.

    Parameters
    ----------
    scheme_extractions   : Output of run_figure_extraction().
    completeness_reports : Output of check_completeness() — one report per scheme.
    text_org             : Output of run_text_organisation().
    id_dict              : Output of run_identifier_dictionary().

    Returns
    -------
    List of fill results, one per scheme.  Each dict has:
        figure_id     : str
        filled_output : dict  (updated reaction_steps with names + conditions)
        unfilled_fields : list
    """
    if not scheme_extractions:
        return []

    prompt_text = _load_prompt()
    report_by_fig = {r.get("figure_id"): r for r in completeness_reports}
    results = []

    for scheme in scheme_extractions:
        figure_id = scheme.get("figure_id", "unknown")
        logger.info(f"[fill_scheme_missing_fields] Filling {figure_id} …")

        report = report_by_fig.get(figure_id, {})

        if settings.PIPELINE_MODE == "real" and prompt_text:
            fill_result = _fill_with_llm(scheme, report, text_org, id_dict, prompt_text, figure_id)
        else:
            fill_result = _fill_rule_based(scheme, id_dict, figure_id)

        fill_result["figure_id"] = figure_id
        results.append(fill_result)

    return results


# ── Internal helpers (new path) ───────────────────────────────────────────────

def _fill_with_llm(
    scheme: dict,
    report: dict,
    text_org: dict,
    id_dict: dict,
    prompt_text: str,
    figure_id: str,
) -> dict:
    """One GPT-4o call per scheme using the Module 6 prompt."""
    if not settings.OPENAI_API_KEY:
        return _fill_rule_based(scheme, id_dict, figure_id)

    extraction_json = json.dumps({
        "reaction_paths": scheme.get("reaction_paths", []),
        "step_analysis":  scheme.get("step_analysis", {}),
    }, indent=2)

    text_evidence = _build_text_evidence(text_org)
    dict_evidence = _build_dict_evidence(id_dict)
    completeness  = json.dumps(report, indent=2)

    user_content = (
        f"Preliminary reaction extraction JSON:\n{extraction_json}\n\n"
        f"Completeness check report:\n{completeness}\n\n"
        f"Organised text evidence:\n{text_evidence}\n\n"
        f"Compound identifier dictionary:\n{dict_evidence}"
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
        n_unfilled = len(result.get("unfilled_fields", []))
        logger.info(
            f"[fill_scheme_missing_fields] {figure_id}: "
            f"{n_unfilled} field(s) still unfilled after LLM fill"
        )
        return result

    except Exception as exc:
        logger.warning(f"[fill_scheme_missing_fields] LLM call failed for {figure_id}: {exc}")
        return _fill_rule_based(scheme, id_dict, figure_id)


def _fill_rule_based(scheme: dict, id_dict: dict, figure_id: str) -> dict:
    """
    Rule-based fill: look up compound names from id_dict for any steps
    where donor/acceptor/product are present but have no compound_name.
    Used in mock mode and as LLM fallback.
    """
    resolved = id_dict.get("resolved", {})
    step_analysis = scheme.get("step_analysis", {})
    steps = step_analysis.get("reaction_steps", [])

    filled_steps = []
    unfilled: list = []

    for step in steps:
        step = dict(step)  # shallow copy
        if step.get("reaction_type") == "glycosylation":
            for role in ("donor", "acceptor", "product"):
                cid = step.get(role)
                if cid and isinstance(cid, str):
                    entry = resolved.get(cid, {})
                    name  = entry.get("compound_name") or entry.get("possible_name")
                    step[role] = {
                        "compound_id":   cid,
                        "compound_name": name,
                        "status":        "verified" if name else "unresolved",
                        "evidence_text": entry.get("evidence_text", ""),
                        "source_type":   "compound_dictionary" if name else None,
                    }
                    if not name:
                        unfilled.append({
                            "step":  step.get("step"),
                            "field": f"{role}_name",
                            "reason": "No verified compound name in dictionary.",
                        })
        filled_steps.append(step)

    filled_step_analysis = dict(step_analysis)
    filled_step_analysis["reaction_steps"] = filled_steps

    return {
        "filled_output": {
            "phase":          filled_step_analysis.get("phase"),
            "reaction_steps": filled_steps,
        },
        "unfilled_fields": unfilled,
    }


def _build_text_evidence(text_org: dict) -> str:
    parts = []
    for cat in ("synthesis_procedures", "general_procedures", "figure_captions"):
        for block in text_org.get(cat, [])[:5]:
            ev = block.get("evidence_text", block.get("text", ""))
            if ev:
                parts.append(f"[{cat}] {ev[:400]}")
    return "\n\n".join(parts)[:6000]


def _build_dict_evidence(id_dict: dict) -> str:
    lines = []
    for cid, entry in list(id_dict.get("resolved", {}).items())[:30]:
        name = entry.get("compound_name") or entry.get("possible_name", "")
        ev   = entry.get("evidence_text", "")
        lines.append(f"{cid}: {name}  [{ev[:80]}]")
    return "\n".join(lines)


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
        logger.warning(f"[fill_scheme_missing_fields] Could not load prompt: {exc}")
        return ""


# ── Legacy path (ReactionRecord) ─────────────────────────────────────────────

def fill_missing_fields(
    record: ReactionRecord,
    supporting_chunks: Dict[str, List[str]],
    text_org: Optional[dict] = None,
    id_dict: Optional[dict] = None,
) -> ReactionRecord:
    """
    Legacy: fill NR fields in a flat ReactionRecord.
    Kept for backward compatibility.
    """
    for field, chunks in supporting_chunks.items():
        attr = "yield_" if field == "yield" else field
        if getattr(record, attr, "NR") != "NR":
            continue
        value, source = _extract_from_chunks(field, chunks)
        if value:
            if field == "solvent":
                value = normalize_solvent(value)
            elif field == "temperature":
                value = normalize_temperature(value)
            setattr(record, attr, value)
            record.provenance[field] = source
            logger.debug(f"Filled '{field}' = '{value}' from: {source[:80]}")

    if id_dict:
        _backfill_from_id_dict(record, id_dict)

    if settings.PIPELINE_MODE == "real":
        _legacy_fill_with_llm(record, supporting_chunks, text_org, id_dict)

    for chunks in supporting_chunks.values():
        for text in chunks:
            if text not in record.supporting_chunks:
                record.supporting_chunks.append(text)

    return record


def _extract_from_chunks(field: str, chunks: List[str]) -> tuple:
    patterns = PATTERNS.get(field, [])
    for chunk_text in chunks:
        for pat in patterns:
            m = re.search(pat, chunk_text, re.IGNORECASE)
            if m:
                return m.group(1).strip(), chunk_text[:200]
    return "", ""


def _backfill_from_id_dict(record: ReactionRecord, id_dict: dict) -> None:
    resolved = id_dict.get("resolved", {})
    if record.donor_id != "NR" and record.donor_name == "NR":
        name = resolved.get(record.donor_id, {}).get("possible_name", "")
        if name:
            record.donor_name = name
            record.provenance["donor_name"] = "id_dict_branch_b"
    if record.acceptor_id != "NR" and record.acceptor_name == "NR":
        name = resolved.get(record.acceptor_id, {}).get("possible_name", "")
        if name:
            record.acceptor_name = name
            record.provenance["acceptor_name"] = "id_dict_branch_b"
    if record.product_id != "NR" and record.product_name == "NR":
        name = resolved.get(record.product_id, {}).get("possible_name", "")
        if name:
            record.product_name = name
            record.provenance["product_name"] = "id_dict_branch_b"


def _legacy_fill_with_llm(
    record: ReactionRecord,
    supporting_chunks: Dict[str, List[str]],
    text_org: Optional[dict],
    id_dict: Optional[dict],
) -> None:
    still_nr = [
        f for f in TRACKED_FIELDS
        if getattr(record, "yield_" if f == "yield" else f, "NR") == "NR"
    ]
    if not still_nr or not settings.OPENAI_API_KEY:
        return

    try:
        from openai import OpenAI
        import json as _json
        client = OpenAI(api_key=settings.OPENAI_API_KEY)
    except ImportError:
        return

    context_parts = []
    for field, chunks in supporting_chunks.items():
        for c in chunks[:2]:
            context_parts.append(c[:200])
    if text_org:
        for cat in ("synthesis_procedures", "general_procedures"):
            for chunk in text_org.get(cat, [])[:3]:
                ev = chunk.get("evidence_text", chunk.get("text", ""))
                context_parts.append(ev[:200])
    if id_dict:
        for label, entry in list(id_dict.get("resolved", {}).items())[:10]:
            name = entry.get("possible_name", "")
            if name:
                context_parts.append(f"{label}: {name}")

    context      = "\n".join(context_parts)[:3000]
    fields_desc  = ", ".join(still_nr)
    prompt = (
        f"You are a chemistry expert extracting data from a glycosylation paper.\n"
        f"Based on the context below, fill in the following fields: {fields_desc}.\n"
        f"Reply with a JSON object where keys are field names and values are the "
        f"extracted values (or null if not found).\n\n"
        f"Context:\n{context}\n\n"
        f"Current known values: "
        f"donor_id={record.donor_id}, acceptor_id={record.acceptor_id}, "
        f"promoter={record.promoter}, solvent={record.solvent}"
    )

    try:
        resp   = client.chat.completions.create(
            model="gpt-4o",
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"},
            max_tokens=300,
        )
        result = _json.loads(resp.choices[0].message.content)
        for field in still_nr:
            attr  = "yield_" if field == "yield" else field
            value = result.get(field)
            if value and value != "null" and isinstance(value, str):
                if field == "solvent":
                    value = normalize_solvent(value)
                elif field == "temperature":
                    value = normalize_temperature(value)
                setattr(record, attr, value)
                record.provenance[field] = "llm_fill_missing_fields"
    except Exception as exc:
        logger.error(f"[fill_missing_fields] LLM call failed: {exc}")
