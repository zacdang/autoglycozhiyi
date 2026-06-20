"""
Figure Relevance Decision — classify which figures are relevant to glycosylation
synthesis (Module 2.03).

In real mode each figure image is sent to GPT-4o vision with the prompt from
configs/prompts/02_03_Synthesis-related Figure Check.md.  The model returns:
  { "is_synthesis_related": bool, "figure_type": str,
    "confidence": "high"|"medium"|"low", "reason": str }

DataRaider-confirmed figures are always relevant (confidence = 1.0).
In mock mode keyword matching is used for test stability.
"""

import base64
import json
from pathlib import Path
from typing import List

from configs import settings
from src.models.figure import Figure
from src.utils.text_utils import contains_glycosylation_keyword
from src.utils.logging_utils import get_logger

logger = get_logger(__name__)

_PROMPT_PATH = (
    Path(__file__).parents[2]
    / "configs" / "prompts"
    / "02_03_figure_relevance.md"
)

CONFIDENCE_THRESHOLD = 0.3
_CONF_MAP = {"high": 0.9, "medium": 0.6, "low": 0.3}


def classify_relevant_figures(unified: dict) -> List[dict]:
    """
    Score each figure in *unified["figures"]* and return those deemed relevant.

    Parameters
    ----------
    unified : The merged extraction dict from merge_extractions().

    Returns
    -------
    List of figure dicts (Figure.to_dict()) with is_relevant=True,
    sorted by relevance_confidence descending.
    """
    all_figures = unified.get("figures", [])

    dataraider_confirmed = {
        t["table_id"]
        for t in unified.get("tables", [])
        if t.get("source") == "dataraider"
    }

    relevant = []

    for fig_dict in all_figures:
        figure = Figure.from_dict(fig_dict)

        # DataRaider confirmation always wins.
        image_stem = Path(figure.image_path).stem if figure.image_path else ""
        if image_stem in dataraider_confirmed:
            figure.is_relevant          = True
            figure.relevance_confidence = 1.0
            figure.relevance_reasons    = ["dataraider_confirmed"]
            relevant.append(figure.to_dict())
            logger.debug(f"Figure {figure.figure_id} → relevant (dataraider_confirmed)")
            continue

        if settings.PIPELINE_MODE != "real":
            # Mock: keyword matching on caption / text labels.
            combined_text = figure.caption + " " + " ".join(figure.text_labels)
            hits = contains_glycosylation_keyword(combined_text)
            confidence = min(len(hits) / 5.0, 1.0)
            reasons    = [f"keyword: {kw}" for kw in hits]
        else:
            confidence, reasons = _classify_with_vision(figure)

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

def _classify_with_vision(figure: Figure) -> tuple:
    """
    Real-mode classification using Module 2.03 prompt + GPT-4o vision.

    Returns (confidence: float, reasons: list[str]).
    Falls back to keyword matching if the image cannot be read or the call fails.
    """
    if not settings.OPENAI_API_KEY:
        return _keyword_fallback(figure, label="no_api_key")

    prompt_text = _load_prompt()
    if not prompt_text:
        return _keyword_fallback(figure, label="prompt_missing")

    # Load and base64-encode the figure image.
    image_b64 = _encode_image(figure.image_path)
    if not image_b64:
        # No image available — fall back to text classification on caption.
        return _classify_text_only(figure, prompt_text)

    try:
        from openai import OpenAI
        client = OpenAI(api_key=settings.OPENAI_API_KEY)
        resp = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text",      "text": prompt_text},
                        {"type": "image_url", "image_url": {
                            "url": f"data:image/png;base64,{image_b64}",
                            "detail": "high",
                        }},
                    ],
                }
            ],
            response_format={"type": "json_object"},
            max_tokens=128,
        )
        raw    = resp.choices[0].message.content
        result = json.loads(raw)

        is_related = bool(result.get("is_synthesis_related", False))
        conf_str   = result.get("confidence", "low")
        conf_val   = _CONF_MAP.get(conf_str, 0.3)
        confidence = conf_val if is_related else 0.0
        fig_type   = result.get("figure_type", "unknown")
        reason     = result.get("reason", "llm_vision")
        return confidence, [f"vision:{fig_type} — {reason}"]

    except Exception as exc:
        logger.debug(f"[classify_relevant_figures] Vision call failed for {figure.figure_id}: {exc}")
        return _keyword_fallback(figure, label="vision_error")


def _classify_text_only(figure: Figure, prompt_text: str) -> tuple:
    """Text-only GPT-4o fallback when the image file is missing."""
    text = (figure.caption + " " + " ".join(figure.text_labels))[:600].strip()
    if not text:
        return 0.0, ["no_text_for_classification"]
    try:
        from openai import OpenAI
        import json as _json
        client = OpenAI(api_key=settings.OPENAI_API_KEY)
        resp = client.chat.completions.create(
            model="gpt-4o",
            messages=[{"role": "user", "content": f"{prompt_text}\n\nCaption/labels:\n{text}"}],
            response_format={"type": "json_object"},
            max_tokens=128,
        )
        result   = _json.loads(resp.choices[0].message.content)
        is_rel   = bool(result.get("is_synthesis_related", False))
        conf_str = result.get("confidence", "low")
        conf_val = _CONF_MAP.get(conf_str, 0.3)
        confidence = conf_val if is_rel else 0.0
        reason     = result.get("reason", "text_only_llm")
        return confidence, [f"text_llm: {reason}"]
    except Exception as exc:
        logger.debug(f"[classify_relevant_figures] Text-only LLM failed: {exc}")
        return _keyword_fallback(figure, label="text_llm_error")


def _keyword_fallback(figure: Figure, label: str = "fallback") -> tuple:
    combined = figure.caption + " " + " ".join(figure.text_labels)
    hits     = contains_glycosylation_keyword(combined)
    return min(len(hits) / 5.0, 1.0), [f"{label}:{kw}" for kw in hits]


def _encode_image(image_path: str) -> str:
    """Return base64-encoded PNG string, or empty string on failure."""
    if not image_path:
        return ""
    try:
        data = Path(image_path).read_bytes()
        return base64.b64encode(data).decode("utf-8")
    except Exception:
        return ""


def _load_prompt() -> str:
    """Extract the prompt text block from the Module 2.03 markdown file."""
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
        logger.warning(f"[classify_relevant_figures] Could not load prompt: {exc}")
        return ""
