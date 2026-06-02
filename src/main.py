"""
Entry point for the autoglyco pipeline.

Usage
-----
    python -m src.main                        # process all registered papers
    python -m src.main --paper PAPER_001      # process one specific paper
    python -m src.main --metadata path/to/papers.json

The pipeline runs in mock mode by default (no external tools needed).
Set PIPELINE_MODE=real in your .env file to use real MERMaid / CDE.
"""

import argparse
import sys
from pathlib import Path

from configs import settings
from src.pipeline.register_papers import register_papers
from src.pipeline.run_pipeline    import run_pipeline
from src.utils.logging_utils      import get_logger

logger = get_logger(__name__)


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description="Glycosylation reaction extraction pipeline"
    )
    parser.add_argument(
        "--paper",
        metavar="PAPER_ID",
        help="Process only this paper ID (default: all registered papers)",
    )
    parser.add_argument(
        "--metadata",
        metavar="PATH",
        default=None,
        help="Path to paper metadata JSON (default: data/samples/sample_paper_metadata.json)",
    )
    return parser.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)

    logger.info(f"Pipeline mode: {settings.PIPELINE_MODE}")

    # Load paper list
    metadata_path = Path(args.metadata) if args.metadata else None
    papers = register_papers(metadata_path)

    # Optionally filter to a single paper
    if args.paper:
        papers = [p for p in papers if p.paper_id == args.paper]
        if not papers:
            logger.error(f"No paper with ID '{args.paper}' found in metadata")
            return 1

    if not papers:
        logger.warning("No papers to process")
        return 0

    # Run the pipeline for each paper
    for paper in papers:
        try:
            scheme_results, saved_paths = run_pipeline(paper)
            n_schemes = len(scheme_results)
            n_complete = sum(
                1 for r in scheme_results
                if not r.get("unfilled_fields")
            )
            print(
                f"\n✓ {paper.paper_id}: "
                f"{n_schemes} scheme(s) extracted, {n_complete} fully filled"
            )
            print(f"  Schemes    → {saved_paths.get('final_schemes')}")
            print(f"  Provenance → {saved_paths.get('provenance')}")
        except Exception as exc:
            logger.exception(f"Pipeline failed for {paper.paper_id}: {exc}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
