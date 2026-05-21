"""
Branch B — Identifier Dictionary: CDE candidates + Agent AI resolver.

This module is one of three parallel branches that run after the shared input
layer. It collects candidate compound labels from CDE chemical_mentions and all
text chunks, then uses Agent AI (GPT-4o) in real mode to resolve each unresolved
label to a chemical name or role description.

In mock mode the existing regex-based _try_resolve_name logic from
build_identifier_dictionary is reused unchanged to guarantee test stability.

Architecture position
---------------------
Shared Input Layer
→ Branch B: Identifier Dictionary [CDE candidates + Agent AI resolver]

Tool assignment
---------------
Step 1 — CDE chemical_mentions + text chunks: collect candidate labels
Step 2 — Agent AI (real mode only): resolve each unresolved label
          mock mode: use regex-based _try_resolve_name (same as before)

Returns the same structure as build_identifier_dictionary():
{ "resolved": {...}, "unresolved": {...} }
"""

from configs import settings
from src.pipeline.build_identifier_dictionary import (
    build_identifier_dictionary,
    _try_resolve_name,
    _guess_role,
)
from src.models.identifier import Identifier
from src.utils.text_utils import extract_identifiers_from_text
from src.utils.logging_utils import get_logger

logger = get_logger(__name__)


def run_identifier_dictionary(documents: dict, text_org: dict) -> dict:
    """
    Branch B: CDE candidates + Agent AI identifier resolver.

    Step 1: Use CDE chemical_mentions and all text chunks from text_org to
            collect candidate compound labels.
    Step 2: Resolve each label:
            - mock mode: use existing regex-based _try_resolve_name logic.
            - real mode: for each still-unresolved label, call GPT-4o with
              surrounding context and ask for compound name/role.

    Parameters
    ----------
    documents : Output of load_documents() (provides paper_id).
    text_org  : Output of run_text_organisation() (provides chemical_mentions,
                text_chunks, si_chunks for candidate collection).

    Returns
    -------
    dict with keys:
        "resolved"   : { label: Identifier.to_dict(), ... }
        "unresolved" : { label: Identifier.to_dict(), ... }
    """
    paper_id = documents["paper_id"]
    logger.info(f"[run_identifier_dictionary] Branch B starting for {paper_id}")

    # Build a mock unified dict so we can reuse build_identifier_dictionary()
    # for the mock path and for the initial candidate collection in real mode.
    # The unified dict only needs the keys that build_identifier_dictionary reads.
    unified_mock = {
        "paper_id":   paper_id,
        "text_chunks": text_org.get("text_chunks", []),
        "si_chunks":   text_org.get("si_chunks", []),
        "figures":     [],   # no figures at this stage
    }

    # Step 1: Use the existing build_identifier_dictionary to collect candidates
    # via the regex resolver (works correctly in both mock and real mode).
    id_dict = build_identifier_dictionary(unified_mock)

    # In mock mode we are done — regex resolver is the authoritative path.
    if settings.PIPELINE_MODE != "real":
        logger.info(
            f"[run_identifier_dictionary] mock mode — "
            f"resolved={len(id_dict['resolved'])}, "
            f"unresolved={len(id_dict['unresolved'])}"
        )
        return id_dict

    # ── Real mode: Agent AI resolver for still-unresolved labels ──────────────
    unresolved = id_dict.get("unresolved", {})
    if not unresolved:
        logger.info("[run_identifier_dictionary] All labels already resolved — no LLM needed")
        return id_dict

    if not settings.OPENAI_API_KEY:
        logger.warning(
            "[run_identifier_dictionary] OPENAI_API_KEY not set — skipping LLM resolution"
        )
        return id_dict

    all_chunks = (
        text_org.get("text_chunks", [])
        + text_org.get("si_chunks", [])
    )

    newly_resolved = _resolve_with_llm(list(unresolved.keys()), all_chunks)

    # Move newly resolved labels from unresolved → resolved.
    resolved = id_dict.get("resolved", {})
    still_unresolved = {}
    for label, entry in unresolved.items():
        if label in newly_resolved:
            # Update the entry with the LLM-resolved name.
            entry = dict(entry)
            entry["possible_name"] = newly_resolved[label]
            entry["resolved"]      = True
            entry["confidence"]    = 0.7
            resolved[label] = entry
        else:
            still_unresolved[label] = entry

    logger.info(
        f"[run_identifier_dictionary] Branch B complete for {paper_id}: "
        f"resolved={len(resolved)}, unresolved={len(still_unresolved)}, "
        f"llm_resolved={len(newly_resolved)}"
    )
    return {"resolved": resolved, "unresolved": still_unresolved}


# ── Internal helpers ──────────────────────────────────────────────────────────

def _resolve_with_llm(labels: list, all_chunks: list) -> dict:
    """
    Call GPT-4o to resolve each label to a compound name.

    Returns a dict { label: resolved_name } for successfully resolved labels only.
    """
    try:
        from openai import OpenAI
        import json as _json
    except ImportError:
        logger.warning("[run_identifier_dictionary] openai not installed — skipping LLM resolution")
        return {}

    client = OpenAI(api_key=settings.OPENAI_API_KEY)
    resolved = {}

    # Build a single context string from all chunks (truncated).
    context = " ".join(c.get("text", "")[:200] for c in all_chunks[:20])[:2000]

    for label in labels:
        prompt = (
            f"In a glycosylation chemistry paper the compound label '{label}' appears. "
            f"Based on the following context, what is the full chemical name or "
            f"description of '{label}'? If you cannot determine it, reply null.\n\n"
            f"Context:\n{context}\n\n"
            f"Reply with JSON: {{\"name\": \"<name or null>\"}}"
        )
        try:
            resp = client.chat.completions.create(
                model="gpt-4o",
                messages=[{"role": "user", "content": prompt}],
                response_format={"type": "json_object"},
                max_tokens=80,
            )
            result = _json.loads(resp.choices[0].message.content)
            name = result.get("name")
            if name and name != "null":
                resolved[label] = name
        except Exception as exc:
            logger.debug(f"[run_identifier_dictionary] LLM resolve failed for '{label}': {exc}")

    return resolved
