"""
Step 11 — Save all pipeline outputs to disk.

Saves four JSON files per paper:
1. Final reaction record           → data/outputs/{paper_id}_final.json
2. Intermediate merged data        → data/intermediate/{paper_id}_merged.json
3. Unresolved identifier list      → data/intermediate/{paper_id}_unresolved_ids.json
4. Validation / completeness report→ data/intermediate/{paper_id}_report.json
"""

from pathlib import Path
from typing import Optional

from configs import settings
from src.models.reaction_record import ReactionRecord
from src.utils.json_utils import save_json
from src.utils.logging_utils import get_logger

logger = get_logger(__name__)


def save_outputs(
    record: ReactionRecord,
    unified: dict,
    id_dict: dict,
    output_dir: Optional[Path] = None,
    intermediate_dir: Optional[Path] = None,
) -> dict:
    """
    Persist all outputs to disk and return a dict of saved file paths.

    Parameters
    ----------
    record           : Final validated ReactionRecord.
    unified          : Merged extraction dict (MERMaid + CDE).
    id_dict          : Identifier dictionary (resolved + unresolved entries).
    output_dir       : Where to save the final reaction JSON.
    intermediate_dir : Where to save supporting/debug JSON files.

    Returns
    -------
    dict mapping output_name → str(path)
    """
    output_dir       = Path(output_dir       or settings.OUTPUT_DIR)
    intermediate_dir = Path(intermediate_dir or settings.INTERMEDIATE_DIR)
    paper_id         = record.paper_id

    paths = {}

    # 1. Final reaction record
    final_path = output_dir / f"{paper_id}_final.json"
    save_json(record.to_dict(), final_path)
    paths["final_record"] = str(final_path)

    # 2. Intermediate merged extraction
    merged_path = intermediate_dir / f"{paper_id}_merged.json"
    save_json(unified, merged_path)
    paths["merged_extraction"] = str(merged_path)

    # 3. Unresolved identifiers only
    unresolved_path = intermediate_dir / f"{paper_id}_unresolved_ids.json"
    save_json(id_dict.get("unresolved", {}), unresolved_path)
    paths["unresolved_ids"] = str(unresolved_path)

    # 4. Validation / completeness report
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
