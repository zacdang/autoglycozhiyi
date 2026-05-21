"""
Step 1 — Register papers.

Reads paper metadata from a local JSON file and returns a list of Paper objects.
In the future, this module can be extended to query Crossref, Europe PMC,
PubMed, or other literature databases.
"""

from pathlib import Path
from typing import List, Optional

from configs import settings
from src.models.paper import Paper
from src.utils.json_utils import load_json
from src.utils.logging_utils import get_logger

logger = get_logger(__name__)


def register_papers(metadata_path: Optional[Path] = None) -> List[Paper]:
    """
    Load paper metadata from a JSON file and return Paper objects.

    Parameters
    ----------
    metadata_path : Path to the JSON file.
                    Defaults to configs.settings.SAMPLE_PAPER_METADATA.

    Returns
    -------
    List[Paper] — one Paper per entry in the JSON array.

    JSON format expected
    --------------------
    [
      {
        "paper_id": "PAPER_001",
        "title":    "...",
        "doi":      "10.1021/...",
        "year":     2023,
        "pdf_path": "data/raw/papers/paper_001.pdf",
        "si_path":  "data/raw/si/paper_001_si.pdf"   // optional
      },
      ...
    ]

    TODO: Replace or extend this function to pull records from:
          - Crossref API (https://api.crossref.org/)
          - Europe PMC (https://europepmc.org/RestfulWebService)
          - PubMed Entrez API
    """
    path = Path(metadata_path or settings.SAMPLE_PAPER_METADATA)
    logger.info(f"Loading paper metadata from {path}")

    raw_list = load_json(path)
    if not isinstance(raw_list, list):
        raise ValueError(f"Expected a JSON array in {path}, got {type(raw_list)}")

    papers = [Paper.from_dict(entry) for entry in raw_list]
    logger.info(f"Registered {len(papers)} paper(s)")
    return papers
