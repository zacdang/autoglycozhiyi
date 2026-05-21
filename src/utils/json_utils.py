"""
Helpers for reading and writing JSON files safely.
"""

import json
from pathlib import Path
from typing import Any

from src.utils.logging_utils import get_logger

logger = get_logger(__name__)


def load_json(path: Path) -> Any:
    """Load a JSON file and return the parsed object."""
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"JSON file not found: {path}")
    with path.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def save_json(data: Any, path: Path, indent: int = 2) -> None:
    """Save an object to a JSON file, creating parent directories as needed."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=indent, ensure_ascii=False)
    logger.debug(f"Saved JSON → {path}")


def pretty_print(data: Any) -> str:
    """Return a pretty-printed JSON string (for debugging)."""
    return json.dumps(data, indent=2, ensure_ascii=False)
