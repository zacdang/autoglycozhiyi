"""
Branch B — Identifier Dictionary: CDE candidates + Agent AI resolver.

In real mode a single GPT-4o call receives all main-article and SI text and
returns verified compound name–ID pairs plus unresolved mentions, as defined
in configs/prompts/02_02_si_dictionary.md.

In mock mode the existing regex-based build_identifier_dictionary logic is
used unchanged for test stability.
"""

import json
from pathlib import Path

from configs import settings
from src.pipeline.build_identifier_dictionary import build_identifier_dictionary
from src.utils.logging_utils import get_logger

logger = get_logger(__name__)

_PROMPT_PATH = Path(__file__).parents[2] / "configs" / "prompts" / "02_02_si_dictionary.md"


def run_identifier_dictionary(documents: dict, text_org: dict) -> dict:
    """
    Branch B: CDE candidates + Agent AI identifier resolver.

    Parameters
    ----------
    documents : Output of load_documents() (provides paper_id, text_blocks, si_blocks).
    text_org  : Output of run_text_organisation().

    Returns
    -------
    dict with keys:
        "resolved"   : { label: { compound_id, compound_name, evidence_text, ... } }
        "unresolved" : { label: { compound_id, reason, evidence_text } }
    """
    paper_id = documents["paper_id"]
    logger.info(f"[run_identifier_dictionary] Branch B starting for {paper_id}")

    # Mock mode: use existing regex resolver.
    if settings.PIPELINE_MODE != "real":
        unified_mock = {
            "paper_id":   paper_id,
            "text_chunks": text_org.get("text_chunks", []),
            "si_chunks":   text_org.get("si_chunks", []),
            "figures":     [],
        }
        id_dict = build_identifier_dictionary(unified_mock)
        logger.info(
            f"[run_identifier_dictionary] mock — "
            f"resolved={len(id_dict['resolved'])}, unresolved={len(id_dict['unresolved'])}"
        )
        return id_dict

    # Real mode: one GPT-4o call that extracts all compound name–ID pairs at once.
    text_blocks = documents.get("text_blocks", [])
    si_blocks   = documents.get("si_blocks", [])
    main_text   = "\n\n".join(b.get("text", b) if isinstance(b, dict) else str(b)
                              for b in text_blocks)
    si_text     = "\n\n".join(b.get("text", b) if isinstance(b, dict) else str(b)
                              for b in si_blocks)

    llm_result = _extract_with_llm(main_text, si_text, paper_id)

    resolved   = {}
    unresolved = {}

    for entry in llm_result.get("verified_compounds", []):
        cid = entry.get("compound_id", "")
        if cid:
            resolved[cid] = {
                "compound_id":   cid,
                "compound_name": entry.get("compound_name", ""),
                "evidence_text": entry.get("evidence_text", ""),
                "possible_name": entry.get("compound_name", ""),
                "role_guess":    "unknown",
                "resolved":      True,
                "confidence":    0.9,
                "source":        "llm_batch",
            }

    for entry in llm_result.get("unresolved_mentions", []):
        cid = entry.get("compound_id", "")
        if cid and cid not in resolved:
            unresolved[cid] = {
                "compound_id":   cid,
                "compound_name": None,
                "evidence_text": entry.get("evidence_text", ""),
                "possible_name": None,
                "role_guess":    "unknown",
                "resolved":      False,
                "confidence":    0.0,
                "reason":        entry.get("reason", ""),
                "source":        "llm_batch",
            }

    # Fall back to regex resolver for any labels the LLM didn't see.
    if not resolved and not unresolved:
        unified_mock = {
            "paper_id":   paper_id,
            "text_chunks": text_org.get("text_chunks", []),
            "si_chunks":   text_org.get("si_chunks", []),
            "figures":     [],
        }
        id_dict = build_identifier_dictionary(unified_mock)
        resolved   = id_dict.get("resolved", {})
        unresolved = id_dict.get("unresolved", {})

    logger.info(
        f"[run_identifier_dictionary] Branch B complete for {paper_id}: "
        f"resolved={len(resolved)}, unresolved={len(unresolved)}"
    )
    return {"resolved": resolved, "unresolved": unresolved}


# ── Internal helpers ──────────────────────────────────────────────────────────

def _extract_with_llm(main_text: str, si_text: str, paper_id: str) -> dict:
    """
    One GPT-4o call that extracts all compound name–ID pairs (Module 2.02 prompt).
    Returns dict with verified_compounds and unresolved_mentions lists.
    Falls back to empty dict on failure.
    """
    if not settings.OPENAI_API_KEY:
        logger.warning("[run_identifier_dictionary] OPENAI_API_KEY not set — skipping LLM")
        return {}

    system_prompt = _load_system_prompt()
    if not system_prompt:
        return {}

    main_excerpt = main_text[:40_000]
    si_excerpt   = si_text[:40_000]

    user_content = (
        f"Main Article:\n{main_excerpt}\n\n"
        f"Supporting Information:\n{si_excerpt}\n\n"
        f"Return your answer as valid JSON only, "
        f"with keys 'verified_compounds' and 'unresolved_mentions'."
    )

    try:
        from openai import OpenAI
        client = OpenAI(api_key=settings.OPENAI_API_KEY)
        resp = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user",   "content": user_content},
            ],
            response_format={"type": "json_object"},
            max_tokens=4096,
        )
        raw = resp.choices[0].message.content
        result = json.loads(raw)
        logger.info(
            f"[run_identifier_dictionary] LLM extracted "
            f"{len(result.get('verified_compounds', []))} verified, "
            f"{len(result.get('unresolved_mentions', []))} unresolved for {paper_id}"
        )
        return result

    except Exception as exc:
        logger.warning(f"[run_identifier_dictionary] LLM call failed for {paper_id}: {exc}")
        return {}


def _load_system_prompt() -> str:
    """Extract the prompt text block from the Module 2.02 markdown file."""
    try:
        md = _PROMPT_PATH.read_text(encoding="utf-8")
        start = md.find("```text\n")
        if start == -1:
            start = md.find("```\n")
        end = md.find("\n```", start + 4)
        if start != -1 and end != -1:
            return md[start + md[start:].find("\n") + 1 : end].strip()
        return md.strip()
    except Exception as exc:
        logger.warning(f"[run_identifier_dictionary] Could not load prompt file: {exc}")
        return ""
