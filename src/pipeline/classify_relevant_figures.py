"""
Step 5 — Classify which figures are relevant to glycosylation synthesis.

Uses rule-based keyword matching on captions and figure text labels.
Each figure receives a confidence score and a list of reasons.

TODO: Replace or extend with an LLM call using configs/prompts/classify_figure.txt.
"""

from typing import List

from src.models.figure import Figure
from src.utils.text_utils import contains_glycosylation_keyword
from src.utils.logging_utils import get_logger

logger = get_logger(__name__)

# Minimum keyword hit count to classify a figure as relevant.
CONFIDENCE_THRESHOLD = 0.3


def classify_relevant_figures(unified: dict) -> List[dict]:
    """
    Score each figure in *unified["figures"]* and return those deemed relevant.

    Two signals are combined:
    1. Keyword matching on captions / text labels (works well with mock data
       or PDFs where VisualHeist captured text).
    2. DataRaider confirmation — if GPT-4o already extracted a reaction table
       from a figure's image, that figure is definitively relevant (confidence 1.0).
       This covers real-mode runs where VisualHeist saves images without text.

    Parameters
    ----------
    unified : The merged extraction dict from merge_extractions().

    Returns
    -------
    List of figure dicts (Figure.to_dict()) with is_relevant=True,
    sorted by relevance_confidence descending.
    """
    all_figures = unified.get("figures", [])

    # Build a set of image stems that DataRaider produced tables for.
    # Table IDs are the image filename stems (e.g. "sianturi_2024_image_8").
    dataraider_confirmed = {
        t["table_id"]
        for t in unified.get("tables", [])
        if t.get("source") == "dataraider"
    }

    relevant = []

    for fig_dict in all_figures:
        figure = Figure.from_dict(fig_dict)

        # Signal 1: keyword matching on caption / text labels.
        combined_text = figure.caption + " " + " ".join(figure.text_labels)
        hits = contains_glycosylation_keyword(combined_text)
        confidence = min(len(hits) / 5.0, 1.0)
        reasons = [f"keyword: {kw}" for kw in hits]

        # Signal 2: DataRaider already extracted data from this image.
        from pathlib import Path
        image_stem = Path(figure.image_path).stem if figure.image_path else ""
        if image_stem in dataraider_confirmed:
            confidence = 1.0
            reasons.append("dataraider_confirmed")

        figure.is_relevant          = confidence >= CONFIDENCE_THRESHOLD
        figure.relevance_confidence = round(confidence, 3)
        figure.relevance_reasons    = reasons

        if figure.is_relevant:
            relevant.append(figure.to_dict())
            logger.debug(
                f"Figure {figure.figure_id} → relevant "
                f"(confidence={figure.relevance_confidence}, hits={reasons})"
            )
        else:
            logger.debug(f"Figure {figure.figure_id} → not relevant (hits={hits})")

    relevant.sort(key=lambda f: f["relevance_confidence"], reverse=True)
    logger.info(f"Classified {len(relevant)}/{len(all_figures)} figure(s) as relevant")
    return relevant
