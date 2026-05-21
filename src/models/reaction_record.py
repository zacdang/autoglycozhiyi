"""
Data model for a single glycosylation reaction record.

Fields marked NR (not reported) when the value could not be extracted.
The completeness_score is computed automatically.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional

# Fields that contribute to the completeness score.
TRACKED_FIELDS = [
    "donor_id", "donor_name",
    "acceptor_id", "acceptor_name",
    "product_id", "product_name",
    "promoter", "solvent", "temperature", "time", "yield", "stereochemistry",
    "procedure_reference",
]


@dataclass
class ReactionRecord:
    """Final structured output for one glycosylation reaction."""

    paper_id:  str
    title:     str = ""
    doi:       str = ""
    figure_id: str = ""

    # Core reaction participants
    donor_id:       str = "NR"
    donor_name:     str = "NR"
    acceptor_id:    str = "NR"
    acceptor_name:  str = "NR"
    product_id:     str = "NR"
    product_name:   str = "NR"

    # Reaction conditions
    promoter:       str = "NR"
    solvent:        str = "NR"
    temperature:    str = "NR"
    time:           str = "NR"
    yield_:         str = "NR"          # underscore avoids clash with built-in
    stereochemistry:str = "NR"

    # Extra context
    glycan_or_substrate_notes: str = ""
    procedure_reference:       str = "NR"

    # All reaction rows extracted by DataRaider (one entry per table row).
    # Populated for synthesis papers that have many reactions rather than one.
    reaction_rows: List[dict] = field(default_factory=list)

    # Provenance and quality
    supporting_chunks:  List[str]       = field(default_factory=list)
    provenance:         Dict[str, str]  = field(default_factory=dict)
    completeness_score: float           = 0.0
    unresolved_fields:  List[str]       = field(default_factory=list)

    def compute_completeness(self) -> float:
        """
        Calculate the fraction of TRACKED_FIELDS that are not 'NR'.
        Updates self.completeness_score and self.unresolved_fields in place.
        """
        resolved = 0
        unresolved = []
        for f in TRACKED_FIELDS:
            # "yield" is stored as "yield_" in the dataclass
            attr = "yield_" if f == "yield" else f
            val = getattr(self, attr, "NR")
            if val and val != "NR":
                resolved += 1
            else:
                unresolved.append(f)
        self.completeness_score = round(resolved / len(TRACKED_FIELDS), 3)
        self.unresolved_fields  = unresolved
        return self.completeness_score

    def to_dict(self) -> dict:
        """Serialize to a plain dictionary matching schema.json."""
        return {
            "paper_id":                   self.paper_id,
            "title":                      self.title,
            "doi":                        self.doi,
            "figure_id":                  self.figure_id,
            "donor_id":                   self.donor_id,
            "donor_name":                 self.donor_name,
            "acceptor_id":                self.acceptor_id,
            "acceptor_name":              self.acceptor_name,
            "product_id":                 self.product_id,
            "product_name":               self.product_name,
            "promoter":                   self.promoter,
            "solvent":                    self.solvent,
            "temperature":                self.temperature,
            "time":                       self.time,
            "yield":                      self.yield_,
            "stereochemistry":            self.stereochemistry,
            "glycan_or_substrate_notes":  self.glycan_or_substrate_notes,
            "procedure_reference":        self.procedure_reference,
            "reaction_rows":              self.reaction_rows,
            "supporting_chunks":          self.supporting_chunks,
            "provenance":                 self.provenance,
            "completeness_score":         self.completeness_score,
            "unresolved_fields":          self.unresolved_fields,
        }
