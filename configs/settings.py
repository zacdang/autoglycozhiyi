"""
Global configuration loaded from environment variables.
Copy .env.example to .env and adjust before running.
"""

import hashlib
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

# ── LLM settings ─────────────────────────────────────────────────────────────
LLM_MODEL: str = os.getenv("LLM_MODEL", "gpt-4o")

# ── Data directories ─────────────────────────────────────────────────────────
DATA_DIR           = ROOT_DIR / os.getenv("DATA_DIR",           "data")
RUNS_DIR           = ROOT_DIR / os.getenv("RUNS_DIR",           "data/runs")
SAMPLES_DIR        = ROOT_DIR / os.getenv("SAMPLES_DIR",        "data/samples")
MERMAID_OUTPUT_DIR = ROOT_DIR / os.getenv("MERMAID_OUTPUT_DIR", "data/mermaid_outputs")
CDE_OUTPUT_DIR     = ROOT_DIR / os.getenv("CDE_OUTPUT_DIR",     "data/cde_outputs")
PARSED_DIR         = ROOT_DIR / os.getenv("PARSED_DIR",         "data/parsed")

# Legacy flat dirs — kept so old code that references them still resolves.
# New code should call run_dirs(paper_id) instead.
INTERMEDIATE_DIR   = ROOT_DIR / os.getenv("INTERMEDIATE_DIR",   "data/intermediate")
OUTPUT_DIR         = ROOT_DIR / os.getenv("OUTPUT_DIR",         "data/outputs")

# ── Config files ──────────────────────────────────────────────────────────────
SCHEMA_PATH  = ROOT_DIR / "configs" / "schema.json"
PROMPTS_DIR  = ROOT_DIR / "configs" / "prompts"

# ── Sample data files (used in mock mode) ────────────────────────────────────
SAMPLE_PAPER_METADATA = SAMPLES_DIR / "sample_paper_metadata.json"
SAMPLE_MERMAID_OUTPUT = SAMPLES_DIR / "sample_mermaid_output.json"
SAMPLE_CDE_OUTPUT     = SAMPLES_DIR / "sample_cde_output.json"
SAMPLE_FINAL_OUTPUT   = SAMPLES_DIR / "sample_final_output.json"

# ── OpenAI (required for DataRaider in real mode) ────────────────────────────
OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")

# ── Module feature flags ──────────────────────────────────────────────────────
# SI extraction (Module 2.04) is paused by default until the SI pipeline is
# stable.  Set ENABLE_SI_EXTRACTION=true in .env to turn it on.
# When false: run_si_extraction() is never called, no SI prompts are built,
# no OpenAI tokens are spent on SI, and si_data = {} flows through to export
# (SI-owned fields stay NR / si_required in audit logs).
ENABLE_SI_EXTRACTION: bool = os.getenv("ENABLE_SI_EXTRACTION", "false").lower() == "true"

# ── Parallelism ───────────────────────────────────────────────────────────────
# Max concurrent GPT-4o vision calls in Module 3.
# Keep ≤ 3 to stay under the 30 k TPM rate limit for image-heavy requests.
FIGURE_EXTRACTION_WORKERS: int = int(os.getenv("FIGURE_EXTRACTION_WORKERS", "2"))

# Max retries per figure before giving up (exponential backoff: 2s, 4s, 8s).
FIGURE_EXTRACTION_MAX_RETRIES: int = int(os.getenv("FIGURE_EXTRACTION_MAX_RETRIES", "3"))

# ── MERMaid repo path (needed for its Prompts/ directory) ────────────────────
# Resolve relative to project root so a path like "../MERMaid" works.
_mermaid_raw = os.getenv("MERMAID_REPO_PATH", "../MERMaid")
MERMAID_REPO_PATH: Path = (ROOT_DIR / _mermaid_raw).resolve()
MERMAID_PROMPTS_DIR: Path = MERMAID_REPO_PATH / "Prompts"


# ── Paper-scoped run directories ─────────────────────────────────────────────

def run_dirs(paper_id: str) -> dict:
    """
    Return a dict of per-paper directories:
        intermediate : data/runs/{paper_id}/intermediate/
        outputs      : data/runs/{paper_id}/outputs/

    Both are created on first access.  This is the canonical way for pipeline
    modules to resolve where to read/write files for a given paper.
    """
    base = RUNS_DIR / paper_id
    dirs = {
        "base":         base,
        "intermediate": base / "intermediate",
        "outputs":      base / "outputs",
    }
    for d in dirs.values():
        d.mkdir(parents=True, exist_ok=True)
    return dirs


# ── Cache-key helper ─────────────────────────────────────────────────────────

def cache_key(paper_id: str, pdf_path: Path, prompt_path: Path) -> str:
    """
    Return an 8-char hex digest that changes whenever any of these change:
        • the source PDF content
        • the prompt file content
        • the LLM model name
        • PIPELINE_MODE

    Usage::

        key  = settings.cache_key(paper_id, pdf_path, prompt_path)
        path = intermediate_dir / f"{paper_id}_id_dict_{key}.json"

    If a file is missing, its hash contribution is just a zero string so the
    function never raises.
    """
    h = hashlib.md5()
    h.update(LLM_MODEL.encode())
    h.update(PIPELINE_MODE.encode())
    for path in (pdf_path, prompt_path):
        try:
            h.update(path.read_bytes())
        except Exception:
            h.update(b"\x00")
    return h.hexdigest()[:8]
