"""
Smoke test — runs the full mock pipeline end-to-end and verifies that:
1. The pipeline completes without exceptions.
2. A final JSON file is written to disk.
3. The final record has the expected structure.
4. The completeness score is above a minimum threshold.
"""

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# Force mock mode for tests regardless of .env settings.
import os
os.environ["PIPELINE_MODE"] = "mock"

from configs import settings
from src.pipeline.register_papers         import register_papers
from src.pipeline.run_pipeline            import run_pipeline


@pytest.fixture(scope="module")
def pipeline_result():
    """Run the full mock pipeline once and share the result across tests."""
    papers = register_papers()
    assert papers, "No papers were registered"
    paper = papers[0]
    record, saved_paths = run_pipeline(paper)
    return record, saved_paths


class TestPipelineSmoke:
    def test_pipeline_runs_without_error(self, pipeline_result):
        record, saved_paths = pipeline_result
        assert record is not None

    def test_final_json_file_written(self, pipeline_result):
        record, saved_paths = pipeline_result
        final_path = Path(saved_paths["final_record"])
        assert final_path.exists(), f"Final output file not found: {final_path}"

    def test_final_json_is_valid(self, pipeline_result):
        record, saved_paths = pipeline_result
        final_path = Path(saved_paths["final_record"])
        with final_path.open() as fh:
            data = json.load(fh)
        assert isinstance(data, dict)

    def test_required_fields_present(self, pipeline_result):
        record, _ = pipeline_result
        d = record.to_dict()
        for field in ["paper_id", "figure_id", "donor_id", "acceptor_id",
                      "product_id", "completeness_score"]:
            assert field in d and d[field] not in (None, ""), (
                f"Required field '{field}' is missing or empty"
            )

    def test_donor_id_not_nr(self, pipeline_result):
        record, _ = pipeline_result
        assert record.donor_id != "NR", "donor_id should be resolved in mock mode"

    def test_acceptor_id_not_nr(self, pipeline_result):
        record, _ = pipeline_result
        assert record.acceptor_id != "NR", "acceptor_id should be resolved in mock mode"

    def test_product_id_not_nr(self, pipeline_result):
        record, _ = pipeline_result
        assert record.product_id != "NR", "product_id should be resolved in mock mode"

    def test_completeness_score_above_threshold(self, pipeline_result):
        record, _ = pipeline_result
        # In mock mode, most fields should be filled → expect at least 50%
        assert record.completeness_score >= 0.5, (
            f"Completeness score too low: {record.completeness_score}"
        )

    def test_intermediate_files_written(self, pipeline_result):
        _, saved_paths = pipeline_result
        for key in ("merged_extraction", "unresolved_ids", "report"):
            path = Path(saved_paths[key])
            assert path.exists(), f"Intermediate file '{key}' not found: {path}"

    def test_provenance_is_dict(self, pipeline_result):
        record, _ = pipeline_result
        assert isinstance(record.provenance, dict)

    def test_supporting_chunks_is_list(self, pipeline_result):
        record, _ = pipeline_result
        assert isinstance(record.supporting_chunks, list)
