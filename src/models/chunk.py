"""
Data model for a text chunk (paragraph, caption, table note, SI block, etc.).
"""

from dataclasses import dataclass
from typing import Optional


@dataclass
class Chunk:
    """
    A unit of text extracted from a paper or its SI.

    source_type can be: "main_text", "si_text", "caption", "table_note", "procedure"
    """

    chunk_id: str
    text: str
    source_type: str          # e.g. "main_text", "si_text", "caption"
    section: Optional[str] = None
    page: Optional[int] = None

    def to_dict(self) -> dict:
        return {
            "chunk_id":    self.chunk_id,
            "text":        self.text,
            "source_type": self.source_type,
            "section":     self.section,
            "page":        self.page,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Chunk":
        return cls(
            chunk_id    = data["chunk_id"],
            text        = data["text"],
            source_type = data["source_type"],
            section     = data.get("section"),
            page        = data.get("page"),
        )
