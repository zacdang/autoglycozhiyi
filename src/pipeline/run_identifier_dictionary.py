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

def _join_wrapped_lines(text: str) -> str:
    """
    Join lines that were wrapped by the PDF extractor so that compound
    headings like:

        5-(tert-Butyl)-2-methylphenyl-2,3-di-O-benzoyl-\n
        butyldiphenylsilyl-1-thio-β-D-galactofuranoside (10)

    become a single line. Rules:
    - If a line ends with a hyphen, join directly to the next line (word-wrap)
    - If a line ends without sentence-ending punctuation (., ?, !)
      AND the next line starts with a lowercase letter or '(' → join with a space
    Blank lines (paragraph separators) are always preserved.
    """
    import re
    lines = text.split("\n")
    out = []
    i = 0
    while i < len(lines):
        line = lines[i]
        # Preserve blank lines as paragraph separators
        if not line.strip():
            out.append(line)
            i += 1
            continue
        # Look ahead and decide whether to join
        while i + 1 < len(lines):
            next_line = lines[i + 1]
            if not next_line.strip():
                break   # blank line → stop joining
            if line.rstrip().endswith("-"):
                # Hard hyphen wrap — keep the hyphen, it's part of the chemical name
                line = line.rstrip() + next_line.lstrip()
                i += 1
            elif not re.search(r'[.!?]\s*$', line.rstrip()) and re.match(r'^[a-z\(]', next_line.lstrip()):
                # Soft wrap — join with space
                line = line.rstrip() + " " + next_line.lstrip()
                i += 1
            else:
                break
        out.append(line)
        i += 1
    return "\n".join(out)


def _extract_with_llm(main_text: str, si_text: str, paper_id: str) -> dict:
    """
    Extract all compound name-ID pairs by chunking the SI by paragraph and
    calling GPT-4o once per chunk. Results are merged across chunks.

    The main article is sent with every chunk (it's short enough).
    SI is split at paragraph boundaries to avoid cutting mid-compound.
    """
    if not settings.OPENAI_API_KEY:
        logger.warning("[run_identifier_dictionary] OPENAI_API_KEY not set — skipping LLM")
        return {}

    system_prompt = _load_system_prompt()
    if not system_prompt:
        return {}

    # Fix wrapped lines before chunking
    si_text = _join_wrapped_lines(si_text)

    # Split SI into paragraph-aware chunks (~60k chars each)
    SI_CHUNK_SIZE = 60_000
    paragraphs = [p.strip() for p in si_text.split("\n\n") if p.strip()]
    si_chunks, current, current_len = [], [], 0
    for para in paragraphs:
        para_len = len(para) + 2
        if current_len + para_len > SI_CHUNK_SIZE and current:
            si_chunks.append("\n\n".join(current))
            current, current_len = [], 0
        current.append(para)
        current_len += para_len
    if current:
        si_chunks.append("\n\n".join(current))

    main_excerpt = main_text[:40_000]
    logger.info(
        f"[run_identifier_dictionary] SI {len(si_text)} chars → "
        f"{len(si_chunks)} chunk(s) to process"
    )

    all_verified   = {}   # compound_id → entry (deduplicated)
    all_unresolved = {}

    try:
        import time
        from openai import OpenAI
        client = OpenAI(api_key=settings.OPENAI_API_KEY)

        for chunk_idx, si_chunk in enumerate(si_chunks):
            user_content = (
                f"Main Article:\n{main_excerpt}\n\n"
                f"Supporting Information (part {chunk_idx + 1} of {len(si_chunks)}):\n{si_chunk}\n\n"
                f"Return valid JSON only with keys 'verified_compounds' and 'unresolved_mentions'."
            )
            try:
                time.sleep(3)
                resp = client.chat.completions.create(
                    model="gpt-4o",
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user",   "content": user_content},
                    ],
                    response_format={"type": "json_object"},
                    max_tokens=8192,
                )
                raw = resp.choices[0].message.content
                if not raw:
                    continue
                result = json.loads(raw)

                for entry in result.get("verified_compounds", []):
                    cid = str(entry.get("compound_id", "")).strip()
                    if not cid:
                        continue
                    new_name = entry.get("compound_name", "")
                    if cid not in all_verified:
                        all_verified[cid] = entry
                    else:
                        # Prefer the longer/more specific name (IUPAC > short label)
                        existing_name = all_verified[cid].get("compound_name", "")
                        if len(new_name) > len(existing_name):
                            all_verified[cid] = entry

                for entry in result.get("unresolved_mentions", []):
                    cid = str(entry.get("compound_id", "")).strip()
                    if cid and cid not in all_verified and cid not in all_unresolved:
                        all_unresolved[cid] = entry

                logger.info(
                    f"[run_identifier_dictionary] chunk {chunk_idx + 1}: "
                    f"+{len(result.get('verified_compounds', []))} verified "
                    f"(total so far: {len(all_verified)})"
                )

            except Exception as chunk_exc:
                logger.warning(
                    f"[run_identifier_dictionary] chunk {chunk_idx + 1} failed: {chunk_exc} — skipping"
                )
                continue

        logger.info(
            f"[run_identifier_dictionary] LLM extracted "
            f"{len(all_verified)} verified, {len(all_unresolved)} unresolved for {paper_id}"
        )
        return {
            "verified_compounds":   list(all_verified.values()),
            "unresolved_mentions":  list(all_unresolved.values()),
        }

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
