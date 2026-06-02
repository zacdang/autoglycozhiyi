# autoglyco

A modular Python pipeline for automated extraction of glycosylation reaction
data from scientific papers using **MERMaid** (multimodal PDF/figure extraction)
and **ChemDataExtractor** (chemistry-aware text parsing).

---

## Why wrap MERMaid and ChemDataExtractor?

Both tools have their own interfaces, output formats, and installation quirks.
Calling them directly throughout the codebase would make it hard to:

- **Swap one tool out** without touching every file that uses it.
- **Test the rest of the pipeline** when a tool is not installed.
- **Add chemistry-specific logic** (donor/acceptor assignment, identifier
  resolution, validation) on top of generic extraction output.

This project wraps each tool behind a clean Python adapter with a **mock mode**
so the entire pipeline can run — and be tested — using bundled sample data,
with no external tools installed.

---

## Project structure

```
autoglyco/
├── README.md
├── requirements.txt
├── .env.example                 ← copy to .env and edit
├── configs/
│   ├── settings.py              ← all config loaded from .env
│   ├── schema.json              ← JSON schema for a reaction record
│   └── prompts/
│       ├── classify_figure.txt  ← prompt template (future LLM use)
│       ├── fill_missing_fields.txt
│       └── validate_record.txt
├── data/
│   ├── raw/papers/              ← input PDFs
│   ├── raw/si/                  ← supplementary information PDFs
│   ├── mermaid_outputs/         ← raw MERMaid JSON (auto-created)
│   ├── cde_outputs/             ← raw CDE JSON (auto-created)
│   ├── intermediate/            ← merged data, reports (auto-created)
│   ├── outputs/                 ← final reaction JSONs (auto-created)
│   └── samples/                 ← bundled mock data for development
│       ├── sample_paper_metadata.json
│       ├── sample_mermaid_output.json
│       ├── sample_cde_output.json
│       └── sample_final_output.json
├── src/
│   ├── main.py                  ← CLI entry point
│   ├── adapters/
│   │   ├── mermaid_adapter.py       ← MERMaid wrapper (mock + real placeholder)
│   │   └── chemdataextractor_adapter.py  ← CDE wrapper (mock + real placeholder)
│   ├── models/
│   │   ├── paper.py             ← Paper dataclass
│   │   ├── figure.py            ← Figure dataclass
│   │   ├── chunk.py             ← Chunk dataclass
│   │   ├── identifier.py        ← Identifier dataclass
│   │   └── reaction_record.py   ← ReactionRecord + completeness scoring
│   ├── pipeline/
│   │   ├── register_papers.py           ← Step 1: load paper metadata
│   │   ├── run_mermaid.py               ← Step 2: MERMaid extraction
│   │   ├── run_chemdataextractor.py     ← Step 3: CDE parsing
│   │   ├── merge_extractions.py         ← Step 4: unify outputs
│   │   ├── classify_relevant_figures.py ← Step 5: keyword-based filtering
│   │   ├── build_identifier_dictionary.py← Step 6: label → name mapping
│   │   ├── assign_roles.py              ← Step 7: donor/acceptor/product
│   │   ├── retrieve_supporting_chunks.py← Step 8: find evidence for NR fields
│   │   ├── fill_missing_fields.py       ← Step 9: regex fill + TODO LLM
│   │   ├── validate_and_normalize.py    ← Step 10: sanity check + scoring
│   │   ├── save_outputs.py              ← Step 11: write JSONs
│   │   └── run_pipeline.py              ← Step 12: orchestrator
│   └── utils/
│       ├── file_utils.py
│       ├── json_utils.py
│       ├── logging_utils.py
│       └── text_utils.py            ← keywords, normalization, regex helpers
└── tests/
    ├── test_schema.py           ← validates configs/schema.json
    └── test_pipeline_smoke.py   ← end-to-end mock pipeline test
```

---

## What each pipeline step does

| Step | Module | Purpose |
|------|--------|---------|
| 1 | `register_papers.py` | Load paper metadata (title, DOI, PDF paths) from JSON |
| 2 | `run_mermaid.py` | Extract figures, tables, text blocks via MERMaid adapter |
| 3 | `run_chemdataextractor.py` | Parse chemical names and conditions via CDE adapter |
| 4 | `merge_extractions.py` | Combine both outputs into one unified internal dict |
| 5 | `classify_relevant_figures.py` | Score figures by glycosylation keyword presence |
| 6 | `build_identifier_dictionary.py` | Map labels like "3a" to chemical names/descriptions |
| 7 | `assign_roles.py` | Assign donor / acceptor / product from figure + id_dict |
| 8 | `retrieve_supporting_chunks.py` | Find best text chunks for each NR field |
| 9 | `fill_missing_fields.py` | Fill NR fields using regex; TODO LLM hooks included |
| 10 | `validate_and_normalize.py` | Expand abbreviations, check plausibility, score record |
| 11 | `save_outputs.py` | Write final + intermediate + unresolved + report JSON |
| 12 | `run_pipeline.py` | Orchestrate steps 1–11 for one paper |

---

## Quick start (mock mode — no external tools needed)

```bash
# 1. Clone / download the project
cd autoglyco

# 2. Create and activate a virtual environment
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Copy the example env file
cp .env.example .env
# Leave PIPELINE_MODE=mock (the default)

# 5. Run the pipeline
python -m src.main

# The final reaction JSON will be written to:
#   data/outputs/PAPER_001_final.json
```

---

## Running the tests

```bash
pytest tests/ -v
```

Both tests run in mock mode and do not require MERMaid or CDE to be installed.

---

## How to add a real paper

1. Put your paper PDF in `data/raw/papers/` and SI PDF in `data/raw/si/`.
2. Add an entry to `data/samples/sample_paper_metadata.json`:

```json
{
  "paper_id": "PAPER_002",
  "title":    "Your paper title",
  "doi":      "10.xxxx/...",
  "year":     2024,
  "pdf_path": "data/raw/papers/paper_002.pdf",
  "si_path":  "data/raw/si/paper_002_si.pdf"
}
```

3. In mock mode, the pipeline will still use the bundled sample extractions.
   To use real extractions, follow the sections below.

---

## Replacing the mock with real MERMaid

Open `src/adapters/mermaid_adapter.py` and implement `_run_real()`.
The skeleton is already there with comments showing exactly what to fill in.

1. Install MERMaid following its own documentation.
2. Set `MERMAID_CLI_PATH` in your `.env`.
3. Set `PIPELINE_MODE=real` in your `.env`.
4. Fill in the `subprocess.run()` call inside `_run_real()`.

---

## Replacing the mock with real ChemDataExtractor

Open `src/adapters/chemdataextractor_adapter.py` and implement `_parse_real()`.

1. `pip install ChemDataExtractor2`
2. Set `PIPELINE_MODE=real` in your `.env`.
3. Implement the CDE Document loading code in `_parse_real()` (the skeleton
   is already provided in the comments).

---

## Adding LLM-based filling (future)

The pipeline has `# TODO` markers in two places where an LLM call can be added:

- `src/pipeline/classify_relevant_figures.py` — use `configs/prompts/classify_figure.txt`
- `src/pipeline/fill_missing_fields.py` — use `configs/prompts/fill_missing_fields.txt`
- `src/pipeline/validate_and_normalize.py` — use `configs/prompts/validate_record.txt`

No LangChain or agent framework is required — a simple `anthropic` or `openai`
API call is sufficient.

---

## Output files

| File | Description |
|------|-------------|
| `data/outputs/{paper_id}_final.json` | Final structured reaction record |
| `data/intermediate/{paper_id}_merged.json` | Unified MERMaid + CDE extraction |
| `data/intermediate/{paper_id}_unresolved_ids.json` | Labels that could not be named |
| `data/intermediate/{paper_id}_report.json` | Completeness score and provenance |

---

## Adding more papers to the metadata file

The paper metadata file is just a JSON array. Add as many entries as you like —
the pipeline will process them one by one when you run `python -m src.main`.

To process only one paper:

```bash
python -m src.main --paper PAPER_002
```
