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

import csv
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
    doi: str = "",
    si_data: Optional[dict] = None,
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

    # 6. CSV export — routed to solution or solid template based on phase
    csv_path = export_to_csv(paper_id, final_schemes, output_dir, doi=doi, si_data=si_data or {}, id_dict=id_dict)
    if csv_path:
        paths["csv_export"] = str(csv_path)

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


# ── CSV export ───────────────────────────────────────────────────────────────

# Column headers matching the two ground-truth templates exactly.
_SOLUTION_COLUMNS = [
    "DOI", "Donor_ID", "Donor_Name", "Donor_SMILES",
    "Donor_Mass_mg", "Donor_mmol",
    "Acceptor_ID", "Acceptor_Name", "Acceptor_SMILES",
    "Acceptor_Mass_mg", "Acceptor_mmol", "Equiv.",
    "Activator_1", "Activator_1_Mass_mg", "Activator_1_mmol",
    "Activator_2", "Activator_2_Volume_uL", "Activator_2_mmol",
    "Solvent_Name", "Solvent_Volume_mL",
    "Temperature_1_initial", "Temperature_final_Celsius",
    "Reaction_Time_min",
    "Product_ID", "Product_Name", "Product_Mass_mg",
    "a:b_ratio", "Yield(%)", "Step", "Comments",
]

_SOLID_COLUMNS = [
    "DOI", "Donor_ID", "Donor_Name", "Donor_SMILES",
    "Acceptor_ID", "Deprotected_Group_Type",
    "Donor_mmol", "Equiv.", "Resin_mass_mg",
    "Activator_Name", "Activator_1_volume_mL", "Activator_1_mmol",
    "Solvent_Name", "Solvent_Volume_mL",
    "T1_Celsius", "t1_min", "T2_Celcius", "t2_min",
    "Product_mass_mg", "Product_Name",
    "Yield(%)", "a:b_ratio", "Step", "Comments",
]


def export_to_csv(
    paper_id: str,
    final_schemes: List[dict],
    output_dir: Path,
    doi: str = "",
    si_data: Optional[dict] = None,
    id_dict: Optional[dict] = None,
) -> Optional[Path]:
    """
    Export all glycosylation steps from final_schemes to a CSV file.

    Routes to the solution-phase or solid-phase column template based on
    the phase field in each scheme's final_output.  If a paper contains both
    phases (rare), two separate files are written.

    Parameters
    ----------
    paper_id      : Used to name the output file.
    final_schemes : List of post-processed scheme dicts from post_process_and_save().
    output_dir    : Where to write the CSV.
    doi           : Optional DOI string to fill the DOI column.

    Returns
    -------
    Path to the CSV file written, or None if no glycosylation steps found.
    """
    solution_rows: List[dict] = []
    solid_rows:    List[dict] = []
    si_data = si_data or {}

    for scheme in final_schemes:
        final = scheme.get("final_output", {})
        phase = final.get("phase", "unknown").lower()
        steps = final.get("reaction_steps", [])

        for step in steps:
            if step.get("reaction_type") != "glycosylation":
                continue

            step_num = step.get("step", "")

            # ── Helper to safely get a nested compound field ──────────────────
            def _cid(role):
                v = step.get(role)
                return v.get("compound_id", "") if isinstance(v, dict) else (v or "")

            def _cname(role):
                v = step.get(role)
                return v.get("compound_name", "") if isinstance(v, dict) else ""

            donor_id   = _cid("donor")
            donor_name = _cname("donor")
            acc_id     = _cid("acceptor")
            acc_name   = _cname("acceptor")
            prod_id    = _cid("product")
            prod_name  = _cname("product")

            # ── Fall back to id_dict for any missing names ────────────────────
            resolved = (id_dict or {}).get("resolved", {})
            def _lookup_name(cid, name):
                if name:
                    return name
                entry = resolved.get(str(cid)) or resolved.get(cid)
                if entry:
                    return entry.get("compound_name") or entry.get("possible_name") or ""
                return ""
            donor_name = _lookup_name(donor_id, donor_name)
            acc_name   = _lookup_name(acc_id,   acc_name)
            prod_name  = _lookup_name(prod_id,  prod_name)

            # ── SI data for this product (fills masses, mmol, SMILES) ─────────
            # si_data is keyed by product_id → experimental dict
            si = si_data.get(str(prod_id), {}) or {}

            if phase == "solid":
                c = step.get("solid_conditions") or {}
                if not c:
                    # Fall back: Module 7 may have used a flat "conditions" key
                    flat = step.get("conditions") or {}
                    c = {
                        "activator_name":        flat.get("promoter_or_activator", ""),
                        "solvent_name":          flat.get("solvent", ""),
                        "T1_celsius":            flat.get("temperature", ""),
                        "t1_min":                flat.get("time", ""),
                        "yield_percent":         flat.get("yield", ""),
                        "a_b_ratio":             flat.get("stereoselectivity", ""),
                    }

                def _vs(si_key, c_key=None):
                    si_val = si.get(si_key)
                    if si_val not in (None, "", "null"):
                        return si_val
                    return c.get(c_key or si_key, "") or ""

                solid_rows.append({
                    "DOI":                   doi,
                    "Donor_ID":              si.get("donor_id") or donor_id,
                    "Donor_Name":            donor_name,
                    "Donor_SMILES":          _vs("donor_smiles"),
                    "Acceptor_ID":           si.get("acceptor_id") or acc_id,
                    "Deprotected_Group_Type": _vs("deprotected_group_type"),
                    "Donor_mmol":            _vs("donor_mmol"),
                    "Equiv.":                _vs("equivalents"),
                    "Resin_mass_mg":         _vs("resin_mass_mg"),
                    "Activator_Name":        _vs("activator_1_name", "activator_name"),
                    "Activator_1_volume_mL": _vs("activator_1_volume_mL", "activator_volume_mL"),
                    "Activator_1_mmol":      _vs("activator_1_mmol", "activator_mmol"),
                    "Solvent_Name":          _vs("solvent_name"),
                    "Solvent_Volume_mL":     _vs("solvent_volume_mL"),
                    "T1_Celsius":            _vs("temperature_initial_celsius", "T1_celsius"),
                    "t1_min":                _vs("t1_min"),
                    "T2_Celcius":            _vs("temperature_final_celsius", "T2_celsius"),
                    "t2_min":                _vs("t2_min"),
                    "Product_mass_mg":       _vs("product_mass_mg"),
                    "Product_Name":          prod_name,
                    "Yield(%)":              _vs("yield_percent"),
                    "a:b_ratio":             _vs("a_b_ratio"),
                    "Step":                  step_num,
                    "Comments":              _vs("comments"),
                })
            else:
                c = step.get("solution_conditions") or {}
                if not c:
                    # Fall back: Module 7 may have used a flat "conditions" key
                    flat = step.get("conditions") or {}
                    c = {
                        "activator_1_name":              flat.get("promoter_or_activator", ""),
                        "solvent_name":                  flat.get("solvent", ""),
                        "temperature_initial_celsius":   flat.get("temperature", ""),
                        "temperature_final_celsius":     flat.get("temperature", ""),
                        "reaction_time_min":             flat.get("time", ""),
                        "yield_percent":                 flat.get("yield", ""),
                        "a_b_ratio":                     flat.get("stereoselectivity", ""),
                    }

                # ── Helper: SI value > figure value > empty ───────────────────
                def _v(si_key, c_key=None):
                    """Return SI value if present, else figure-extracted value."""
                    si_val = si.get(si_key)
                    if si_val not in (None, "", "null"):
                        return si_val
                    return c.get(c_key or si_key, "") or ""

                solution_rows.append({
                    "DOI":                    doi,
                    "Donor_ID":               si.get("donor_id") or donor_id,
                    "Donor_Name":             donor_name,
                    "Donor_SMILES":           _v("donor_smiles"),
                    "Donor_Mass_mg":          _v("donor_mass_mg"),
                    "Donor_mmol":             _v("donor_mmol"),
                    "Acceptor_ID":            si.get("acceptor_id") or acc_id,
                    "Acceptor_Name":          acc_name,
                    "Acceptor_SMILES":        _v("acceptor_smiles"),
                    "Acceptor_Mass_mg":       _v("acceptor_mass_mg"),
                    "Acceptor_mmol":          _v("acceptor_mmol"),
                    "Equiv.":                 _v("equivalents"),
                    "Activator_1":            _v("activator_1_name"),
                    "Activator_1_Mass_mg":    _v("activator_1_mass_mg"),
                    "Activator_1_mmol":       _v("activator_1_mmol"),
                    "Activator_2":            _v("activator_2_name"),
                    "Activator_2_Volume_uL":  _v("activator_2_volume_uL"),
                    "Activator_2_mmol":       _v("activator_2_mmol"),
                    "Solvent_Name":           _v("solvent_name"),
                    "Solvent_Volume_mL":      _v("solvent_volume_mL"),
                    "Temperature_1_initial":  _v("temperature_initial_celsius"),
                    "Temperature_final_Celsius": _v("temperature_final_celsius"),
                    "Reaction_Time_min":      _v("reaction_time_min"),
                    "Product_ID":             prod_id,
                    "Product_Name":           prod_name,
                    "Product_Mass_mg":        _v("product_mass_mg"),
                    "a:b_ratio":              _v("a_b_ratio"),
                    "Yield(%)":               _v("yield_percent"),
                    "Step":                   step_num,
                    "Comments":               _v("comments"),
                })

    if not solution_rows and not solid_rows:
        logger.warning(f"[export_to_csv] No glycosylation steps found for {paper_id}")
        return None

    last_path = None

    if solution_rows:
        path = output_dir / f"{paper_id}_solution.csv"
        _write_csv(path, _SOLUTION_COLUMNS, solution_rows)
        logger.info(f"[export_to_csv] Solution CSV → {path} ({len(solution_rows)} row(s))")
        last_path = path

    if solid_rows:
        path = output_dir / f"{paper_id}_solid.csv"
        _write_csv(path, _SOLID_COLUMNS, solid_rows)
        logger.info(f"[export_to_csv] Solid CSV → {path} ({len(solid_rows)} row(s))")
        last_path = path

    # Always write the Excel file with both tabs
    excel_path = output_dir / "test.xlsx"
    _write_excel(excel_path, _SOLUTION_COLUMNS, solution_rows, _SOLID_COLUMNS, solid_rows)
    logger.info(f"[export_to_csv] Excel → {excel_path} (solution: {len(solution_rows)} row(s), solid: {len(solid_rows)} row(s))")

    return last_path


def _write_csv(path: Path, columns: List[str], rows: List[dict]) -> None:
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def _write_excel(
    path: Path,
    solution_cols: List[str],
    solution_rows: List[dict],
    solid_cols: List[str],
    solid_rows: List[dict],
) -> None:
    """Write test.xlsx with a Solution tab and a Solid tab."""
    try:
        from openpyxl import Workbook
        from openpyxl.styles import Font, PatternFill, Alignment
        from openpyxl.utils import get_column_letter
    except ImportError:
        logger.warning("[export_to_csv] openpyxl not installed — skipping Excel export. Run: pip install openpyxl")
        return

    wb = Workbook()

    # ── Solution tab ──────────────────────────────────────────────────────────
    ws_sol = wb.active
    ws_sol.title = "Solution"
    _fill_sheet(ws_sol, solution_cols, solution_rows)

    # ── Solid tab ─────────────────────────────────────────────────────────────
    ws_sol2 = wb.create_sheet(title="Solid")
    _fill_sheet(ws_sol2, solid_cols, solid_rows)

    wb.save(path)


def _safe_cell_value(v) -> str:
    """Strip XML-illegal control characters so openpyxl never raises IllegalCharacterError."""
    import re
    if v is None:
        return ""
    s = str(v)
    # Remove chars that are illegal in XML 1.0 (openpyxl uses XML internally)
    return re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", s)


def _fill_sheet(ws, columns: List[str], rows: List[dict]) -> None:
    """Write headers + rows into a worksheet with basic formatting."""
    try:
        from openpyxl.styles import Font, PatternFill, Alignment
        from openpyxl.utils import get_column_letter

        HEADER_FILL  = PatternFill("solid", fgColor="4472C4")
        HEADER_FONT  = Font(bold=True, color="FFFFFF")
        HEADER_ALIGN = Alignment(horizontal="center", wrap_text=True)

        # Write header row
        for col_idx, col_name in enumerate(columns, start=1):
            cell = ws.cell(row=1, column=col_idx, value=col_name)
            cell.fill  = HEADER_FILL
            cell.font  = HEADER_FONT
            cell.alignment = HEADER_ALIGN

        # Write data rows
        for row_idx, row_data in enumerate(rows, start=2):
            for col_idx, col_name in enumerate(columns, start=1):
                ws.cell(row=row_idx, column=col_idx,
                        value=_safe_cell_value(row_data.get(col_name, "")))

        # Auto-fit column widths (approximate)
        for col_idx, col_name in enumerate(columns, start=1):
            max_len = max(
                len(str(col_name)),
                *(len(str(r.get(col_name, "") or "")) for r in rows) if rows else [0],
            )
            ws.column_dimensions[get_column_letter(col_idx)].width = min(max_len + 2, 40)

        # Freeze top row
        ws.freeze_panes = "A2"

    except Exception as exc:
        # If styling fails just write plain data
        for col_idx, col_name in enumerate(columns, start=1):
            ws.cell(row=1, column=col_idx, value=col_name)
        for row_idx, row_data in enumerate(rows, start=2):
            for col_idx, col_name in enumerate(columns, start=1):
                ws.cell(row=row_idx, column=col_idx,
                        value=_safe_cell_value(row_data.get(col_name, "")))


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
