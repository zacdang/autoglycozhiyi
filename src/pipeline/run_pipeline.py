"""
Orchestrator — runs the full canonical glycosylation extraction pipeline.

Canonical workflow implemented here:

  Shared Input Layer (Main PDF + SI PDF)
  → Phase Classification              [Agent AI / LLM]
  → Figure/Table Extraction           [MERMaid VisualHeist]
  → BRANCH POINT (3 parallel):
      Branch A: Text Organisation     [CDE primary + Agent AI chunk classifier]
      Branch B: Identifier Dictionary [CDE candidates + Agent AI resolver]
      Branch C: Figure Extraction     [MERMaid VisualHeist outputs]
  → Figure Relevance Decision         [Agent AI]
      NO  → stop (produce minimal record)
      YES → Primary Figure Extraction [MERMaid DataRaider, already done]
  → Completeness Check                [rule-based + optional Agent AI]
      COMPLETE   → Final Output
      INCOMPLETE → Fill Missing Fields (main MERGE node) [Agent AI]
                   ← merges: figure-derived record
                             + Branch A text chunks
                             + Branch B identifier dict
  → loop back to Completeness Check (max 2 iterations)
  → Final Output                      [custom code]
  → Post-processing & Provenance      [custom code]
"""

from src.models.paper import Paper
from src.models.reaction_record import ReactionRecord
from src.pipeline.load_documents            import load_documents
from src.pipeline.classify_phase            import classify_phase
from src.pipeline.run_mermaid               import run_mermaid
from src.pipeline.run_text_organisation     import run_text_organisation
from src.pipeline.run_identifier_dictionary import run_identifier_dictionary
from src.pipeline.merge_extractions         import merge_extractions
from src.pipeline.classify_relevant_figures  import classify_relevant_figures
from src.pipeline.assign_roles              import assign_roles
from src.pipeline.retrieve_supporting_chunks import retrieve_supporting_chunks
from src.pipeline.fill_missing_fields       import fill_missing_fields
from src.pipeline.validate_and_normalize    import validate_and_normalize
from src.pipeline.save_outputs              import save_outputs
from src.utils.logging_utils                import get_logger

logger = get_logger(__name__)

# Maximum completeness-loop iterations before accepting a partial record.
MAX_ITERATIONS = 2


def run_pipeline(paper: Paper) -> tuple:
    """
    Run the full glycosylation extraction pipeline on *paper*.

    Returns
    -------
    (ReactionRecord, saved_paths_dict)
    """
    logger.info(f"=== Starting pipeline for {paper.paper_id} ===")

    # ── 0. Shared Input Layer ─────────────────────────────────────────────────
    # Load raw documents (pdfplumber text blocks) once for all branches.
    documents = load_documents(paper)

    # ── 1. Phase Classification [Agent AI] ────────────────────────────────────
    phase_info = classify_phase(documents)
    logger.info(
        f"Phase classification: {phase_info['phase']} "
        f"(confidence={phase_info['confidence']:.2f})"
    )

    # ── 2. Figure/Table Extraction [MERMaid VisualHeist] ──────────────────────
    # Pass documents so pdfplumber is not run a second time in real mode.
    mermaid_output = run_mermaid(paper, documents=documents)

    # ── 3. Three parallel branches ────────────────────────────────────────────
    # Branch A: Text Organisation [CDE primary + Agent AI chunk classifier]
    text_org = run_text_organisation(documents)

    # Branch B: Identifier Dictionary [CDE candidates + Agent AI resolver]
    id_dict = run_identifier_dictionary(documents, text_org)

    # Branch C: figure outputs are already in mermaid_output (figures, tables).

    # ── 4. Figure Relevance Decision [Agent AI] ───────────────────────────────
    # Merge MERMaid figures with Branch A text chunks for the unified view.
    unified = merge_extractions(mermaid_output, text_org)
    relevant_figures = classify_relevant_figures(unified)

    if not relevant_figures:
        logger.warning(
            f"No relevant figures found for {paper.paper_id}; "
            f"producing minimal record."
        )
        # Produce a mostly-NR minimal record and save it.
        record = ReactionRecord(paper_id=paper.paper_id)
        record.title = paper.title
        record.doi   = paper.doi
        record.phase = phase_info.get("phase", "unknown")
        record = validate_and_normalize(record)
        saved_paths = save_outputs(record, unified, id_dict)
        logger.info(
            f"=== Pipeline complete (no relevant figures) for {paper.paper_id} "
            f"(completeness={record.completeness_score:.0%}) ==="
        )
        return record, saved_paths

    # ── 5. Primary Figure-Based Extraction [DataRaider] ───────────────────────
    # Already done inside run_mermaid → mermaid_output["tables"] contains
    # DataRaider reaction rows.

    # ── 6. Assign Roles → initial record from MERMaid visual branch ──────────
    record = assign_roles(
        paper_id         = paper.paper_id,
        relevant_figures = relevant_figures,
        unified          = unified,
        id_dict          = id_dict,
    )
    record.title = paper.title
    record.doi   = paper.doi
    record.phase = phase_info.get("phase", "unknown")

    # ── 7–9. Completeness Check → decision → fill loop ────────────────────────
    for iteration in range(MAX_ITERATIONS):
        # Completeness Check [rule-based]
        record = validate_and_normalize(record)

        if record.completeness_score >= 0.8 or not record.unresolved_fields:
            logger.info(
                f"COMPLETE after iteration {iteration}: "
                f"score={record.completeness_score:.0%}"
            )
            break   # COMPLETE → exit loop

        # INCOMPLETE → Fill Missing Fields (main MERGE node) [Agent AI]
        logger.info(
            f"INCOMPLETE (iteration {iteration}, "
            f"score={record.completeness_score:.0%}, "
            f"missing={record.unresolved_fields}) — running fill loop"
        )
        supporting_chunks = retrieve_supporting_chunks(record, unified)
        record = fill_missing_fields(
            record,
            supporting_chunks,
            text_org = text_org,
            id_dict  = id_dict,
        )

    # Final validate to ensure completeness_score is up-to-date.
    record = validate_and_normalize(record)

    # ── 10–11. Final Output + Post-processing & Provenance [custom code] ──────
    saved_paths = save_outputs(record, unified, id_dict)

    logger.info(
        f"=== Pipeline complete for {paper.paper_id} "
        f"(completeness={record.completeness_score:.0%}) ==="
    )
    return record, saved_paths
