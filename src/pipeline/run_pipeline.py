"""
Orchestrator — runs the full glycosylation extraction pipeline.

Workflow:

  1. Shared Input Layer     load_documents()
     ↓
  2. Phase Classification   classify_phase()              [Agent AI]
     ↓
  3. MERMaid Extraction     run_mermaid()                 [VisualHeist + DataRaider]
     ↓ ─────────────────── 3 parallel branches ──────────────────────────────────
  Branch A  Text Organisation        run_text_organisation()    [Module 2.01]
  Branch B  Identifier Dictionary    run_identifier_dictionary() [Module 2.02]
  Branch C  Figure outputs from MERMaid (already in mermaid_output)
     ↓
  4. Figure Relevance Decision  classify_relevant_figures()  [Module 2.03 — vision]
     ↓
  5. Primary Figure Extraction  run_figure_extraction()      [Module 3 — vision]
     ↓
  6. Completeness Check  +  Fill Missing Fields loop          [Modules 4 + 5]
     ↓
  7. Post-processing & Provenance  post_process_and_save()    [Module 6]
"""

from pathlib import Path

from src.models.paper import Paper
from src.models.reaction_record import ReactionRecord
from src.pipeline.load_documents             import load_documents
from src.pipeline.classify_phase             import classify_phase
from src.pipeline.run_mermaid                import run_mermaid
from src.pipeline.run_text_organisation      import run_text_organisation
from src.pipeline.run_identifier_dictionary  import run_identifier_dictionary
from src.pipeline.merge_extractions          import merge_extractions
from src.pipeline.classify_relevant_figures  import classify_relevant_figures
from src.pipeline.run_figure_extraction      import run_figure_extraction
from src.pipeline.validate_and_normalize     import check_completeness, validate_and_normalize
from src.pipeline.fill_missing_fields        import fill_scheme_missing_fields, fill_missing_fields
from src.pipeline.assign_roles               import assign_roles
from src.pipeline.retrieve_supporting_chunks import retrieve_supporting_chunks
from src.pipeline.run_si_extraction          import run_si_extraction
from src.pipeline.save_outputs               import post_process_and_save, save_outputs
from src.utils.logging_utils                 import get_logger

logger = get_logger(__name__)

MAX_ITERATIONS = 2


def run_pipeline(paper: Paper) -> tuple:
    """
    Run the full glycosylation extraction pipeline on *paper*.

    Returns
    -------
    (scheme_results, saved_paths_dict)
    where scheme_results is a list of final per-scheme dicts.
    """
    logger.info(f"=== Starting pipeline for {paper.paper_id} ===")

    # ── 1. Shared Input Layer ─────────────────────────────────────────────────
    documents = load_documents(paper)

    # ── 2. Phase Classification ───────────────────────────────────────────────
    phase_info = classify_phase(documents)
    logger.info(
        f"Phase: {phase_info['phase']} (confidence={phase_info['confidence']:.2f})"
    )

    # ── 3. MERMaid Extraction ─────────────────────────────────────────────────
    mermaid_output = run_mermaid(paper, documents=documents)

    # ── 3 branches (A + B run in serial; C is mermaid_output) ────────────────
    text_org = run_text_organisation(documents)
    id_dict  = run_identifier_dictionary(documents, text_org)

    # ── 4. Figure Relevance Decision ──────────────────────────────────────────
    unified          = merge_extractions(mermaid_output, text_org)
    relevant_figures = classify_relevant_figures(unified)

    if not relevant_figures:
        logger.warning(
            f"No relevant figures for {paper.paper_id} — producing minimal output."
        )
        saved_paths = post_process_and_save(
            paper_id             = paper.paper_id,
            fill_results         = [],
            scheme_extractions   = [],
            completeness_reports = [],
            unified              = unified,
            id_dict              = id_dict,
            doi                  = paper.doi or "",
            si_data              = {},
        )
        return [], saved_paths

    # ── 5. Primary Figure Extraction [Module 4] ───────────────────────────────
    scheme_extractions = run_figure_extraction(relevant_figures, text_org, id_dict)

    # ── 6. Completeness Check + Fill Missing Fields loop [Modules 5 + 6] ─────
    completeness_reports = []
    fill_results         = []

    for iteration in range(MAX_ITERATIONS):
        completeness_reports = check_completeness(scheme_extractions, text_org, id_dict)

        all_complete = all(r.get("is_complete", False) for r in completeness_reports)
        if all_complete:
            logger.info(f"All schemes complete after iteration {iteration}")
            # Still run fill once to enrich compound names from id_dict.
            fill_results = fill_scheme_missing_fields(
                scheme_extractions, completeness_reports, text_org, id_dict
            )
            break

        logger.info(
            f"Iteration {iteration}: "
            f"{sum(1 for r in completeness_reports if not r.get('is_complete'))}/"
            f"{len(completeness_reports)} scheme(s) incomplete — filling …"
        )
        fill_results = fill_scheme_missing_fields(
            scheme_extractions, completeness_reports, text_org, id_dict
        )

        # Patch scheme_extractions with filled data for the next iteration.
        scheme_extractions = _patch_extractions(scheme_extractions, fill_results)

    if not fill_results:
        # Ran all iterations without breaking early — do one final fill pass.
        fill_results = fill_scheme_missing_fields(
            scheme_extractions, completeness_reports, text_org, id_dict
        )

    # ── 7a. SI Experimental Extraction [Module 2.04] ─────────────────────────
    # Reads SI text (if available) to fill masses, mmol, volumes, SMILES
    # for each product compound. Results merged into CSV rows by save_outputs.
    from src.utils.json_utils import save_json, load_json
    from configs import settings as _s
    si_data_path = Path(_s.INTERMEDIATE_DIR) / f"{paper.paper_id}_si_data.json"

    if si_data_path.exists():
        si_data = load_json(si_data_path)
        logger.info(f"SI data loaded from cache → {si_data_path} ({len(si_data)} compounds)")
    else:
        si_data = run_si_extraction(documents, scheme_extractions)
        if si_data:
            save_json(si_data, si_data_path)
            logger.info(f"SI data saved → {si_data_path}")

    # Save resolved id_dict for quick re-runs / testing
    if id_dict.get("resolved"):
        id_dict_path = Path(_s.INTERMEDIATE_DIR) / f"{paper.paper_id}_id_dict.json"
        save_json(id_dict, id_dict_path)
        logger.info(f"ID dict saved → {id_dict_path}")

    # ── 7b. Post-processing & Provenance [Module 7] ───────────────────────────
    saved_paths = post_process_and_save(
        paper_id             = paper.paper_id,
        fill_results         = fill_results,
        scheme_extractions   = scheme_extractions,
        completeness_reports = completeness_reports,
        unified              = unified,
        id_dict              = id_dict,
        doi                  = paper.doi or "",
        si_data              = si_data,
    )

    logger.info(
        f"=== Pipeline complete for {paper.paper_id}: "
        f"{len(scheme_extractions)} scheme(s) extracted ==="
    )
    return fill_results, saved_paths


# ── Internal helpers ──────────────────────────────────────────────────────────

def _patch_extractions(scheme_extractions: list, fill_results: list) -> list:
    """
    After a fill pass, update scheme_extractions with the filled step data
    so the next completeness check sees the improvements.
    """
    fill_by_fig = {r.get("figure_id"): r for r in fill_results}
    patched = []
    for scheme in scheme_extractions:
        fig_id = scheme.get("figure_id")
        fill   = fill_by_fig.get(fig_id, {})
        filled = fill.get("filled_output", {})
        if filled:
            scheme = dict(scheme)
            step_analysis = dict(scheme.get("step_analysis", {}))
            if filled.get("reaction_steps"):
                step_analysis["reaction_steps"] = filled["reaction_steps"]
            if filled.get("phase"):
                step_analysis["phase"] = filled["phase"]
            scheme["step_analysis"] = step_analysis
        patched.append(scheme)
    return patched
