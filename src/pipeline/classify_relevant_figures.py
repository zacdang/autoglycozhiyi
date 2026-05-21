"""
Figure Relevance Decision — classify which figures are relevant to glycosylation
synthesis.

Architecture position
---------------------
Branch C figure outputs → Figure Relevance Decision [Agent AI]

Primary signal in real mode: Agent AI (GPT-4o) per-figure classification.
Primary signal in mock mode: rule-based keyword matching (for test stability).
DataRaider-confirmed figures are always relevant (confidence = 1.0).

Two signals are always combined:
1. DataRaider confirmation — if GPT-4o already extracted a reaction table from
   a figure, it is definitively relevant (confidence 1.0).
2. mock mode: keyword matching on captions / text labels.
   real mode:  Agent AI classification (unless already DataRaider-confirmed).
"""

from pathlib import Path
from typing import List

from configs import settings
from src.models.figure import Figure
from src.utils.text_utils import contains_glycosylation_keyword
from src.utils.logging_utils import get_logger

logger = get_logger(__name__)

# Minimum confidence to classify a figure as relevant.
CONFIDENCE_THRESHOLD = 0.3


def classify_relevant_figures(unified: dict) -> List[dict]:
    """
    Score each figure in *unified["figures"]* and return those deemed relevant.

    Signals combined:
    1. DataRaider confirmation — GPT-4o already extracted data → confidence 1.0.
    2. mock mode: keyword matching on captions / text labels.
       real mode: Agent AI (GPT-4o) classification for non-DataRaider figures.

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
    dataraider_confirmed = {
        t["table_id"]
        for t in unified.get("tables", [])
        if t.get("source") == "dataraider"
    }

    relevant = []

    for fig_dict in all_figures:
        figure = Figure.from_dict(fig_dict)

        # Signal 1: DataRaider confirmation — always wins.
        image_stem = Path(figure.image_path).stem if figure.image_path else ""
        if image_stem in dataraider_confirmed:
            figure.is_relevant          = True
            figure.relevance_confidence = 1.0
            figure.relevance_reasons    = ["dataraider_confirmed"]
            relevant.append(figure.to_dict())
            logger.debug(f"Figure {figure.figure_id} → relevant (dataraider_confirmed)")
            continue

        # Signal 2a (mock mode): keyword matching on caption / text labels.
        if settings.PIPELINE_MODE != "real":
            combined_text = figure.caption + " " + " ".join(figure.text_labels)
            hits = contains_glycosylation_keyword(combined_text)
            confidence = min(len(hits) / 5.0, 1.0)
            reasons = [f"keyword: {kw}" for kw in hits]
        else:
            # Signal 2b (real mode): Agent AI classification.
            confidence, reasons = _classify_with_llm(figure)

        figure.is_relevant          = confidence >= CONFIDENCE_THRESHOLD
        figure.relevance_confidence = round(confidence, 3)
        figure.relevance_reasons    = reasons

        if figure.is_relevant:
            relevant.append(figure.to_dict())
            logger.debug(
                f"Figure {figure.figure_id} → relevant "
                f"(confidence={figure.relevance_confidence}, reasons={reasons})"
            )
        else:
            logger.debug(
                f"Figure {figure.figure_id} → not relevant "
                f"(confidence={figure.relevance_confidence})"
            )

    relevant.sort(key=lambda f: f["relevance_confidence"], reverse=True)
    logger.info(f"Classified {len(relevant)}/{len(all_figures)} figure(s) as relevant")
    return relevant


# ── Internal helpers ──────────────────────────────────────────────────────────

def _classify_with_llm(figure: Figure) -> tuple:
    """
    Real-mode Agent AI classification for a single figure.

    Returns (confidence: float, reasons: list[str]).
    Falls back to keyword matching if the OpenAI call fails.
    """
    if not settings.OPENAI_API_KEY:
        # Fallback: keyword matching
        combined = figure.caption + " " + " ".join(figure.text_labels)
        hits = contains_glycosylation_keyword(combined)
        return min(len(hits) / 5.0, 1.0), [f"keyword: {kw}" for kw in hits]

    try:
        from openai import OpenAI
        import json as _json

        client = OpenAI(api_key=settings.OPENAI_API_KEY)
        text   = (figure.caption + " " + " ".join(figure.text_labels))[:600].strip()

        if not text:
            return 0.0, ["no_text_for_classification"]

        prompt = (
            "You are a chemistry expert. Does the following figure caption/label "
            "from a scientific paper describe a glycosylation synthesis reaction table "
            "or scheme? Reply with JSON: {\"relevant\": true/false, \"confidence\": 0-1, "
            "\"reason\": \"one sentence\"}.\n\n"
            f"Caption/labels:\n{text}"
        )
        resp = client.chat.completions.create(
            model="gpt-4o",
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"},
            max_tokens=80,
        )
        result = _json.loads(resp.choices[0].message.content)
        relevant   = bool(result.get("relevant", False))
        confidence = float(result.get("confidence", 0.5)) if relevant else 0.0
        reason     = result.get("reason", "llm_classification")
        return confidence, [f"llm: {reason}"]

    except Exception as exc:
        logger.debug(f"[classify_relevant_figures] LLM call failed for {figure.figure_id}: {exc}")
        # Fallback to keyword matching on failure.
        combined = figure.caption + " " + " ".join(figure.text_labels)
        hits = contains_glycosylation_keyword(combined)
        return min(len(hits) / 5.0, 1.0), [f"keyword_fallback: {kw}" for kw in hits]
