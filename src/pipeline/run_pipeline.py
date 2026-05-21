"""
Step 12 — Orchestrate the full pipeline for one paper.

Calling run_pipeline(paper) runs all steps in sequence and returns
the final ReactionRecord plus a dict of saved file paths.
"""

from src.models.paper import Paper
from src.models.reaction_record import ReactionRecord
from src.pipeline.run_mermaid              import run_mermaid
from src.pipeline.run_chemdataextractor    import run_chemdataextractor
from src.pipeline.merge_extractions        import merge_extractions
from src.pipeline.classify_relevant_figures import classify_relevant_figures
from src.pipeline.build_identifier_dictionary import build_identifier_dictionary
from src.pipeline.assign_roles             import assign_roles
from src.pipeline.retrieve_supporting_chunks import retrieve_supporting_chunks
from src.pipeline.fill_missing_fields      import fill_missing_fields
from src.pipeline.validate_and_normalize   import validate_and_normalize
from src.pipeline.save_outputs             import save_outputs
from src.utils.logging_utils               import get_logger

logger = get_logger(__name__)


def run_pipeline(paper: Paper) -> tuple:
    """
    Run the full glycosylation extraction pipeline on *paper*.

    Returns
    -------
    (ReactionRecord, saved_paths_dict)

    Pipeline steps
    --------------
    1.  run_mermaid              — extract figures/tables/text from PDF
    2.  run_chemdataextractor    — parse chemistry-aware text
    3.  merge_extractions        — combine into unified internal dict
    4.  classify_relevant_figures— find glycosylation synthesis figures
    5.  build_identifier_dictionary — map labels to chemical names
    6.  assign_roles             — build initial ReactionRecord
    7.  retrieve_supporting_chunks — find chunks for missing fields
    8.  fill_missing_fields      — fill NR fields using retrieved chunks
    9.  validate_and_normalize   — normalise values & score completeness
    10. save_outputs             — write all JSONs to disk
    """
    logger.info(f"=== Starting pipeline for {paper.paper_id} ===")

    # Step 1 — MERMaid branch: extract figures / captions / tables / DataRaider
    #           reaction rows from the main PDF and SI PDF → initial reaction
    #           record backbone.
    mermaid_output = run_mermaid(paper)

    # Step 2 — CDE text branch: receives text_blocks produced by the MERMaid
    #           branch above, then runs chemistry-aware text parsing to produce
    #           chemical mentions, condition mentions, and text chunks.
    cde_output = run_chemdataextractor(paper, mermaid_output=mermaid_output)

    # Step 3 — Merge: combine MERMaid visual branch + CDE text branch outputs
    #           into a single unified dict used by all downstream steps.
    unified = merge_extractions(mermaid_output, cde_output)

    # Step 4 — Classify figures
    relevant_figures = classify_relevant_figures(unified)

    # Step 5 — Build identifier dictionary
    id_dict = build_identifier_dictionary(unified)

    # Step 6 — Assign roles → initial record
    record = assign_roles(
        paper_id         = paper.paper_id,
        relevant_figures = relevant_figures,
        unified          = unified,
        id_dict          = id_dict,
    )
    # Populate paper-level metadata
    record.title = paper.title
    record.doi   = paper.doi

    # Step 7 — Retrieve supporting chunks for NR fields
    supporting_chunks = retrieve_supporting_chunks(record, unified)

    # Step 8 — Fill missing fields
    record = fill_missing_fields(record, supporting_chunks)

    # Step 9 — Validate and score
    record = validate_and_normalize(record)

    # Step 10 — Save
    saved_paths = save_outputs(record, unified, id_dict)

    logger.info(
        f"=== Pipeline complete for {paper.paper_id} "
        f"(completeness={record.completeness_score:.0%}) ==="
    )
    return record, saved_paths
