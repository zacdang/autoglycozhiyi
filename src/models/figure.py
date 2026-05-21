"""
Data model for a figure or scheme extracted from a paper.
"""

from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class Figure:
    """Represents a single figure or scheme extracted by MERMaid (or mock)."""

    figure_id: str
    page: int
    caption: str
    image_path: Optional[str] = None
    text_labels: List[str] = field(default_factory=list)
    # Coordinates in the source PDF: [x0, y0, x1, y1]
    bounding_box: Optional[List[float]] = None

    # Filled by classify_relevant_figures
    is_relevant: bool = False
    relevance_confidence: float = 0.0
    relevance_reasons: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "figure_id":            self.figure_id,
            "page":                 self.page,
            "caption":              self.caption,
            "image_path":           self.image_path,
            "text_labels":          self.text_labels,
            "bounding_box":         self.bounding_box,
            "is_relevant":          self.is_relevant,
            "relevance_confidence": self.relevance_confidence,
            "relevance_reasons":    self.relevance_reasons,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Figure":
        return cls(
            figure_id            = data["figure_id"],
            page                 = data["page"],
            caption              = data["caption"],
            image_path           = data.get("image_path"),
            text_labels          = data.get("text_labels", []),
            bounding_box         = data.get("bounding_box"),
            is_relevant          = data.get("is_relevant", False),
            relevance_confidence = data.get("relevance_confidence", 0.0),
            relevance_reasons    = data.get("relevance_reasons", []),
        )
