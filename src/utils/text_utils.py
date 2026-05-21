"""
Text processing helpers: keyword matching, simple normalization, etc.
"""

import re
from typing import List


# Maps common abbreviations to full names used in the reaction record.
SOLVENT_NORMALIZATION: dict = {
    "ch2cl2":    "dichloromethane",
    "dcm":       "dichloromethane",
    "thf":       "tetrahydrofuran",
    "meoh":      "methanol",
    "etoh":      "ethanol",
    "et2o":      "diethyl ether",
    "dmf":       "dimethylformamide",
    "dmso":      "dimethyl sulfoxide",
    "mecn":      "acetonitrile",
    "ch3cn":     "acetonitrile",
    "toluene":   "toluene",
    "benzene":   "benzene",
}

TEMPERATURE_NORMALIZATION: dict = {
    "rt":                   "room temperature",
    "room temperature":     "room temperature",
    "room temp":            "room temperature",
    "r.t.":                 "room temperature",
    "r. t.":                "room temperature",
}

# Keywords that suggest a figure depicts a glycosylation reaction.
GLYCOSYLATION_KEYWORDS: List[str] = [
    "glycosylation", "glycoside", "donor", "acceptor",
    "thioglycoside", "trichloroacetimidate", "nphenyltrifluoroacetimidate",
    "nis", "tfoh", "nbs", "bsi", "tmsi", "tf2o",
    "α-", "β-", "anomer", "anomeric",
    "disaccharide", "oligosaccharide", "glycan",
    "scheme", "synthesis", "coupling",
]


def normalize_solvent(raw: str) -> str:
    """Convert common solvent abbreviations to full names."""
    key = raw.strip().lower().replace(" ", "")
    return SOLVENT_NORMALIZATION.get(key, raw)


def normalize_temperature(raw: str) -> str:
    """Convert 'rt', 'r.t.' etc. to 'room temperature'."""
    key = raw.strip().lower()
    return TEMPERATURE_NORMALIZATION.get(key, raw)


def contains_glycosylation_keyword(text: str) -> List[str]:
    """
    Return a list of glycosylation-related keywords found in *text*.
    An empty list means none were found.
    """
    text_lower = text.lower()
    return [kw for kw in GLYCOSYLATION_KEYWORDS if kw in text_lower]


def keyword_match_score(text: str, keywords: List[str]) -> float:
    """
    Simple keyword overlap score between 0 and 1.
    Useful for ranking supporting chunks.
    """
    if not keywords:
        return 0.0
    text_lower = text.lower()
    hits = sum(1 for kw in keywords if kw.lower() in text_lower)
    return hits / len(keywords)


def extract_identifiers_from_text(text: str) -> List[str]:
    """
    Find alphanumeric compound labels like '3a', '5b', '6c', 'Procedure B'.
    Returns a deduplicated list.
    """
    # Match patterns like: 1a, 3b, 10c, Procedure A, Donor A, etc.
    pattern = r'\b(?:Procedure|Donor|Acceptor|Product|Compound)?\s*\d{1,3}[a-zA-Z]{1,2}\b|\b(?:Procedure|Donor|Acceptor)\s+[A-Z]\b'
    matches = re.findall(pattern, text)
    return list(dict.fromkeys(m.strip() for m in matches))  # preserve order, deduplicate
