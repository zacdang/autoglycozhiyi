"""
Test that the JSON schema (configs/schema.json) is well-formed and that
the sample final output validates against it.
"""

import json
import sys
from pathlib import Path

import pytest

# Make sure project root is on the path so imports work.
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.utils.json_utils import load_json
from configs import settings


def _load_schema():
    return load_json(settings.SCHEMA_PATH)


def _load_sample_final():
    return load_json(settings.SAMPLE_FINAL_OUTPUT)


class TestSchema:
    def test_schema_file_exists(self):
        assert settings.SCHEMA_PATH.exists(), "configs/schema.json not found"

    def test_schema_is_valid_json(self):
        schema = _load_schema()
        assert isinstance(schema, dict)

    def test_schema_has_required_top_level_keys(self):
        schema = _load_schema()
        assert "properties" in schema
        assert "required"   in schema

    def test_schema_required_fields_present(self):
        schema = _load_schema()
        required = set(schema["required"])
        expected = {"paper_id", "figure_id", "donor_id", "acceptor_id",
                    "product_id", "completeness_score"}
        assert expected.issubset(required), (
            f"Missing required fields in schema: {expected - required}"
        )

    def test_schema_properties_include_all_reaction_fields(self):
        schema = _load_schema()
        props = set(schema["properties"].keys())
        expected_fields = {
            "paper_id", "title", "doi", "figure_id",
            "donor_id", "donor_name", "acceptor_id", "acceptor_name",
            "product_id", "product_name",
            "promoter", "solvent", "temperature", "time", "yield",
            "stereochemistry", "glycan_or_substrate_notes",
            "procedure_reference", "supporting_chunks",
            "provenance", "completeness_score", "unresolved_fields",
        }
        missing = expected_fields - props
        assert not missing, f"Schema properties missing: {missing}"

    def test_sample_final_output_matches_schema_structure(self):
        sample = _load_sample_final()
        schema = _load_schema()
        # Check every required field exists in the sample.
        for field in schema["required"]:
            assert field in sample, f"Required field '{field}' missing from sample output"

    def test_completeness_score_in_range(self):
        sample = _load_sample_final()
        score = sample.get("completeness_score", -1)
        assert 0.0 <= score <= 1.0, f"completeness_score {score} out of range [0,1]"
