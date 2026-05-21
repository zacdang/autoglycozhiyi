"""
Filesystem helpers used across the pipeline.
"""

from pathlib import Path
from typing import List


def ensure_dir(path: Path) -> Path:
    """Create directory (and parents) if it does not exist; return the path."""
    path = Path(path)
    path.mkdir(parents=True, exist_ok=True)
    return path


def list_files(directory: Path, extension: str = "") -> List[Path]:
    """
    Return a sorted list of files inside *directory*.
    If *extension* is given (e.g. ".pdf"), only files with that suffix are returned.
    """
    directory = Path(directory)
    if not directory.exists():
        return []
    files = sorted(directory.iterdir())
    if extension:
        files = [f for f in files if f.suffix.lower() == extension.lower()]
    return files


def stem(path: Path) -> str:
    """Return the filename without extension."""
    return Path(path).stem
