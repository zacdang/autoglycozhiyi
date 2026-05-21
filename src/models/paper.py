"""
Data model for a scientific paper registered in the pipeline.
"""

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Paper:
    """Represents a single scientific paper and its associated file paths."""

    paper_id: str
    title: str
    doi: str
    year: int
    pdf_path: str
    si_path: Optional[str] = None

    def to_dict(self) -> dict:
        """Serialize to a plain dictionary for JSON output."""
        return {
            "paper_id": self.paper_id,
            "title":    self.title,
            "doi":      self.doi,
            "year":     self.year,
            "pdf_path": self.pdf_path,
            "si_path":  self.si_path,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Paper":
        """Deserialize from a plain dictionary (e.g. loaded from JSON)."""
        return cls(
            paper_id = data["paper_id"],
            title    = data["title"],
            doi      = data["doi"],
            year     = data["year"],
            pdf_path = data["pdf_path"],
            si_path  = data.get("si_path"),
        )
