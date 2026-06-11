from src.pipeline.pipeline_readiness import build_pipeline_readiness_summary


def test_pipeline_readiness_passes_with_valid_inputs():
    documents = {
        "paper_id": "TEST_001",
        "input_validation": {"valid": True, "errors": [], "warnings": []},
        "text_blocks": [{"text": "A" * 600}],
        "si_blocks": [{"text": "B" * 400}],
    }
    id_dict = {
        "resolved": {
            "S1": {
                "compound_name": "benzyl glycoside",
                "source": "SI",
                "evidence_text": "Compound S1 was prepared from donor S0.",
            }
        },
        "unresolved": {},
    }
    relevant_figures = [
        {
            "figure_id": "fig1",
            "relevance_confidence": 0.9,
            "relevance_reasons": ["keyword: glycosylation"],
        }
    ]

    summary = build_pipeline_readiness_summary(
        documents=documents,
        text_org={},
        id_dict=id_dict,
        relevant_figures=relevant_figures,
    )

    assert summary["ready_for_downstream_extraction"] is True
    assert summary["input_valid"] is True
    assert summary["identifier_quality_summary"]["resolved_count"] == 1
    assert summary["relevant_figure_count"] == 1
    assert summary["warnings"] == []


def test_pipeline_readiness_warns_on_missing_identifier_and_figures():
    documents = {
        "paper_id": "TEST_002",
        "input_validation": {"valid": True, "errors": [], "warnings": []},
        "text_blocks": [{"text": "short"}],
        "si_blocks": [],
    }

    summary = build_pipeline_readiness_summary(
        documents=documents,
        text_org={},
        id_dict={"resolved": {}, "unresolved": {}},
        relevant_figures=[],
    )

    assert summary["ready_for_downstream_extraction"] is False
    assert summary["identifier_quality_summary"]["resolved_count"] == 0
    assert summary["relevant_figure_count"] == 0
    assert any("No resolved identifiers" in warning for warning in summary["warnings"])
    assert any("No relevant synthesis figures" in warning for warning in summary["warnings"])


def test_pipeline_readiness_counts_identifier_quality_issues():
    documents = {
        "paper_id": "TEST_003",
        "input_validation": {"valid": True, "errors": [], "warnings": []},
        "text_blocks": [{"text": "A" * 600}],
        "si_blocks": [{"text": "B" * 400}],
    }
    id_dict = {
        "resolved": {
            "S1": {"compound_name": "", "source": "unknown", "evidence_text": ""},
            "S2": {"possible_name": "acceptor", "source": "SI", "source_text": "S2 was used."},
        },
        "unresolved": {"S3": {"reason": "ambiguous"}},
    }

    summary = build_pipeline_readiness_summary(
        documents=documents,
        text_org={},
        id_dict=id_dict,
        relevant_figures=[{"figure_id": "fig1"}],
    )

    quality = summary["identifier_quality_summary"]
    assert quality["resolved_count"] == 2
    assert quality["unresolved_count"] == 1
    assert quality["missing_name_count"] == 1
    assert quality["missing_evidence_count"] == 1
    assert quality["unknown_source_count"] == 1
    assert any("lack compound names" in warning for warning in summary["warnings"])
