"""
Data model for a compound or procedure identifier (e.g. "3a", "Procedure B").
"""

from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class Identifier:
    """
    Maps an alphanumeric label found in the paper to its possible chemical name
    and the source text it was found in.

    resolved=False means we found the label but could not map it to a name yet.
    """

    identifier: str           # raw label, e.g. "3a", "donor A", "Procedure B"
    possible_name: str        # best guess at a chemical name; "" if unknown
    source_text: str          # the text snippet where this was found
    source_type: str          # "caption", "main_text", "si_text", "table"
    confidence: float = 0.0
    resolved: bool = False
    role_guess: Optional[str] = None  # "donor", "acceptor", "product", "procedure", etc.

    def to_dict(self) -> dict:
        return {
            "identifier":   self.identifier,
            "possible_name":self.possible_name,
            "source_text":  self.source_text,
            "source_type":  self.source_type,
            "confidence":   self.confidence,
            "resolved":     self.resolved,
            "role_guess":   self.role_guess,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Identifier":
        return cls(
            identifier    = data["identifier"],
            possible_name = data.get("possible_name", ""),
            source_text   = data.get("source_text", ""),
            source_type   = data.get("source_type", ""),
            confidence    = data.get("confidence", 0.0),
            resolved      = data.get("resolved", False),
            role_guess    = data.get("role_guess"),
        )
