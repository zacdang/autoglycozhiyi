"""
Global configuration loaded from environment variables.
Copy .env.example to .env and adjust before running.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# Load .env file if present; silently skip if missing.
load_dotenv()

# ── Project root ──────────────────────────────────────────────────────────────
ROOT_DIR = Path(__file__).resolve().parent.parent

# ── Pipeline mode ─────────────────────────────────────────────────────────────
# "mock"  → use pre-built sample JSON files (no external tools needed)
# "real"  → call actual MERMaid / ChemDataExtractor binaries / libraries
PIPELINE_MODE: str = os.getenv("PIPELINE_MODE", "mock")

# ── Data directories ─────────────────────────────────────────────────────────
DATA_DIR          = ROOT_DIR / os.getenv("DATA_DIR",          "data")
SAMPLES_DIR       = ROOT_DIR / os.getenv("SAMPLES_DIR",       "data/samples")
MERMAID_OUTPUT_DIR= ROOT_DIR / os.getenv("MERMAID_OUTPUT_DIR","data/mermaid_outputs")
CDE_OUTPUT_DIR    = ROOT_DIR / os.getenv("CDE_OUTPUT_DIR",    "data/cde_outputs")
PARSED_DIR        = ROOT_DIR / os.getenv("PARSED_DIR",        "data/parsed")
INTERMEDIATE_DIR  = ROOT_DIR / os.getenv("INTERMEDIATE_DIR",  "data/intermediate")
OUTPUT_DIR        = ROOT_DIR / os.getenv("OUTPUT_DIR",        "data/outputs")

# ── Config files ──────────────────────────────────────────────────────────────
SCHEMA_PATH       = ROOT_DIR / "configs" / "schema.json"
PROMPTS_DIR       = ROOT_DIR / "configs" / "prompts"

# ── Sample data files (used in mock mode) ────────────────────────────────────
SAMPLE_PAPER_METADATA = SAMPLES_DIR / "sample_paper_metadata.json"
SAMPLE_MERMAID_OUTPUT = SAMPLES_DIR / "sample_mermaid_output.json"
SAMPLE_CDE_OUTPUT     = SAMPLES_DIR / "sample_cde_output.json"
SAMPLE_FINAL_OUTPUT   = SAMPLES_DIR / "sample_final_output.json"

# ── OpenAI (required for DataRaider in real mode) ────────────────────────────
OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")

# ── MERMaid repo path (needed for its Prompts/ directory) ────────────────────
# Resolve relative to project root so a path like "../MERMaid" works.
_mermaid_raw = os.getenv("MERMAID_REPO_PATH", "../MERMaid")
MERMAID_REPO_PATH: Path = (ROOT_DIR / _mermaid_raw).resolve()
MERMAID_PROMPTS_DIR: Path = MERMAID_REPO_PATH / "Prompts"
