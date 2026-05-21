"""
Phase Classification — determines the synthesis phase of a glycosylation reaction.

This step runs early in the pipeline, before figure/table extraction, and uses a
short excerpt from the document text to classify whether the paper describes
solution-phase or solid-phase glycosylation synthesis.

Architecture position
---------------------
Shared Input Layer → Phase Classification [Agent AI / LLM]

Tool assignment
---------------
mock mode : return hardcoded { "phase": "solution", "confidence": 1.0, ... }
real mode : call OpenAI GPT-4o with the first ~500 chars of text_blocks
"""

from configs import settings
from src.utils.logging_utils import get_logger

logger = get_logger(__name__)


def classify_phase(documents: dict) -> dict:
    """
    Use the first ~500 chars of text_blocks to determine the synthesis phase.

    Parameters
    ----------
    documents : Output of load_documents() — must contain a "text_blocks" list.

    Returns
    -------
    dict with keys:
        phase      : "solution" | "solid" | "unknown"
        confidence : float in [0.0, 1.0]
        reasoning  : short human-readable explanation
    """
    if settings.PIPELINE_MODE != "real":
        logger.info("[classify_phase] mock mode — returning default phase")
        return {
            "phase":      "solution",
            "confidence": 1.0,
            "reasoning":  "mock",
        }

    # ── Real mode: call OpenAI GPT-4o ─────────────────────────────────────────
    if not settings.OPENAI_API_KEY:
        logger.warning("[classify_phase] OPENAI_API_KEY not set — defaulting to unknown")
        return {"phase": "unknown", "confidence": 0.0, "reasoning": "no API key"}

    text_blocks = documents.get("text_blocks", [])
    # Build a short excerpt from the first few blocks.
    excerpt = ""
    for blk in text_blocks:
        excerpt += blk.get("text", "") + " "
        if len(excerpt) >= 500:
            break
    excerpt = excerpt[:500].strip()

    if not excerpt:
        logger.warning("[classify_phase] No text available for phase classification")
        return {"phase": "unknown", "confidence": 0.0, "reasoning": "no text"}

    try:
        from openai import OpenAI
        client = OpenAI(api_key=settings.OPENAI_API_KEY)

        prompt = (
            "You are a chemistry expert. Based on the following excerpt from a "
            "scientific paper about glycosylation, classify the synthesis phase as "
            "'solution' (solution-phase synthesis) or 'solid' (solid-phase synthesis). "
            "Reply with a JSON object with exactly these keys: "
            "phase (string: 'solution', 'solid', or 'unknown'), "
            "confidence (float 0-1), reasoning (one sentence).\n\n"
            f"Excerpt:\n{excerpt}"
        )

        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"},
            max_tokens=150,
        )

        import json
        result = json.loads(response.choices[0].message.content)
        phase      = result.get("phase", "unknown")
        confidence = float(result.get("confidence", 0.5))
        reasoning  = result.get("reasoning", "")

        logger.info(
            f"[classify_phase] phase={phase}, confidence={confidence:.2f}"
        )
        return {"phase": phase, "confidence": confidence, "reasoning": reasoning}

    except Exception as exc:
        logger.error(f"[classify_phase] OpenAI call failed: {exc}")
        return {"phase": "unknown", "confidence": 0.0, "reasoning": str(exc)}
