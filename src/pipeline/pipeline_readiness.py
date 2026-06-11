"""
Workflow readiness checks.

This module summarizes whether the upstream workflow state is sufficient for
downstream extraction and post-processing. It is not tied to a single person's
module; it provides a compact quality-control report for the full pipeline.
"""

from __future__ import annotations

from typing import Any


_TEXT_LENGTH_WARNING_THRESHOLD = 500


def build_pipeline_readiness_summary(
    documents: dict,
    text_org: dict,
    id_dict: dict,
    relevant_figures: list[dict],
) -> dict:
    """
    Build a readiness summary for the current workflow state.

    The summary checks four workflow inputs:
    1. Module 1 input validation report
    2. extracted main/SI text blocks
    3. identifier dictionary quality
    4. relevant figure selection

    Returns a dict designed to be saved as JSON and inspected during workflow
    debugging or reporting.
    """
    input_validation = documents.get("input_validation", {}) or {}
    main_text_length = _total_text_length(documents.get("text_blocks", []))
    si_text_length = _total_text_length(documents.get("si_blocks", []))

    resolved = id_dict.get("resolved", {}) or {}
    unresolved = id_dict.get("unresolved", {}) or {}
    id_quality = _identifier_dictionary_quality(resolved, unresolved)

    warnings = []
    errors = []

    if input_validation and not input_validation.get("valid", True):
        errors.extend(input_validation.get("errors", []))
    warnings.extend(input_validation.get("warnings", []))

    if main_text_length < _TEXT_LENGTH_WARNING_THRESHOLD:
        warnings.append(
            f"Main text is short or missing before downstream extraction: {main_text_length} characters."
        )

    if si_text_length == 0:
        warnings.append("SI text is missing before downstream extraction; identifier resolution may be incomplete.")

    if id_quality["resolved_count"] == 0:
        warnings.append("No resolved identifiers are available for downstream extraction.")

    if id_quality["missing_name_count"] > 0:
        warnings.append(
            f"{id_quality['missing_name_count']} resolved identifier(s) lack compound names."
        )

    if id_quality["missing_evidence_count"] > 0:
        warnings.append(
            f"{id_quality['missing_evidence_count']} resolved identifier(s) lack evidence text."
        )

    if not relevant_figures:
        warnings.append("No relevant synthesis figures selected for downstream extraction.")

    ready_for_downstream_extraction = not errors and bool(relevant_figures)

    return {
        "paper_id": documents.get("paper_id"),
        "ready_for_downstream_extraction": ready_for_downstream_extraction,
        "input_valid": input_validation.get("valid"),
        "main_text_block_count": len(documents.get("text_blocks", []) or []),
        "si_text_block_count": len(documents.get("si_blocks", []) or []),
        "main_text_length": main_text_length,
        "si_text_length": si_text_length,
        "identifier_quality_summary": id_quality,
        "relevant_figure_count": len(relevant_figures or []),
        "relevant_figures": [
            {
                "figure_id": fig.get("figure_id"),
                "relevance_confidence": fig.get("relevance_confidence"),
                "relevance_reasons": fig.get("relevance_reasons", []),
            }
            for fig in (relevant_figures or [])
        ],
        "errors": errors,
        "warnings": warnings,
    }


def _total_text_length(blocks: list[Any]) -> int:
    """Return total character count for dict or string text blocks."""
    total = 0
    for block in blocks or []:
        if isinstance(block, dict):
            total += len(str(block.get("text", "")))
        else:
            total += len(str(block))
    return total


def _identifier_dictionary_quality(resolved: dict, unresolved: dict) -> dict:
    """Summarize identifier dictionary quality for downstream extraction."""
    missing_name = 0
    missing_evidence = 0
    unknown_source = 0

    for entry in resolved.values():
        name = entry.get("compound_name") or entry.get("possible_name") or entry.get("name")
        evidence = entry.get("evidence_text") or entry.get("source_text")
        source = entry.get("source_type") or entry.get("source")

        if not name:
            missing_name += 1
        if not evidence:
            missing_evidence += 1
        if not source or source == "unknown":
            unknown_source += 1

    return {
        "resolved_count": len(resolved),
        "unresolved_count": len(unresolved),
        "missing_name_count": missing_name,
        "missing_evidence_count": missing_evidence,
        "unknown_source_count": unknown_source,
    }
