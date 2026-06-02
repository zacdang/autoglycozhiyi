# autoglyco

An automated pipeline for extracting structured glycosylation reaction data from
carbohydrate chemistry papers. Given a paper PDF (and optionally its Supporting
Information), the pipeline produces a fully-populated CSV/Excel file matching a
standardised reaction data template — ready for database ingestion.

---

## How it works

```
PDF + SI PDF
    │
    ▼
┌─────────────────────────────────────────────────┐
│  Shared Input Layer  (load_documents.py)         │
│  • pdfplumber text extraction (main + SI)        │
│  • auto-download missing PDFs via Unpaywall API  │
└──────────────────────┬──────────────────────────┘
                       │
          ┌────────────┼────────────┐
          ▼            ▼            ▼
   Phase classifier  Text org   Identifier dict
   (GPT-4o)         (GPT-4o    (GPT-4o resolves
                    Module 2.01) compound labels
                                 Module 2.02)
          │
          ▼
┌─────────────────────────────────────────────────┐
│  MERMaid  (VisualHeist + DataRaider)             │
│  • Florence-2 extracts figures from PDF pages   │
│  • GPT-4o vision reads each figure image        │
└──────────────────────┬──────────────────────────┘
                       │
          ┌────────────┴────────────┐
          ▼                         ▼
  Figure relevance check     SI experimental extraction
  (GPT-4o vision             (GPT-4o reads SI text,
   Module 2.03)               extracts masses/mmol/
                               SMILES per compound
                               Module 2.04)
          │
          ▼
┌─────────────────────────────────────────────────┐
│  Primary Figure Extraction  (Module 3)           │
│  GPT-4o vision: donor + acceptor + product IDs, │
│  reaction conditions (solvent, temp, time, yield)│
└──────────────────────┬──────────────────────────┘
                       │
          ┌────────────┴────────────┐
          ▼                         ▼
  Completeness check           Fill missing fields
  (GPT-4o Module 4)            (GPT-4o Module 5)
          └────────────┬────────────┘
                       │  (iterates up to 2×)
                       ▼
┌─────────────────────────────────────────────────┐
│  Post-processing & Provenance  (Module 6)        │
│  GPT-4o standardises field names, marks sources │
└──────────────────────┬──────────────────────────┘
                       │
                       ▼
         solution_PAPER.csv / solid_PAPER.csv
                  test.xlsx (both tabs)
```

---

## Project structure

```
autoglyco/
├── README.md
├── requirements.txt
├── .env.example                    ← copy to .env and add your API key
├── configs/
│   ├── settings.py                 ← all config loaded from .env
│   ├── schema.json
│   └── prompts/                    ← GPT-4o prompt templates (Modules 2–6)
│       ├── 01_input_preparation.md
│       ├── 02_01_text_organization.md
│       ├── 02_02_si_dictionary.md
│       ├── 02_03_Synthesis-related Figure Check.md
│       ├── 02_04_si_experimental.md
│       ├── 03_Primary Figure-based Extraction.md
│       ├── 04_Completeness Check.md
│       ├── 05_Fill Missing Fields.md
│       └── 06_Post-processing & Provenance.md
├── data/
│   ├── raw/papers/                 ← input PDFs (main article + SI)
│   ├── mermaid_outputs/            ← VisualHeist PNGs + DataRaider JSON
│   ├── intermediate/               ← merged data, completeness reports, SI data
│   ├── outputs/                    ← final CSV, Excel, scheme JSON, provenance
│   └── samples/                    ← bundled mock data for development/testing
│       ├── sample_paper_metadata.json
│       ├── sample_mermaid_output.json
│       └── sample_final_output.json
├── src/
│   ├── main.py                     ← CLI entry point
│   ├── adapters/
│   │   ├── mermaid_adapter.py      ← VisualHeist + DataRaider integration
│   │   └── chemdataextractor_adapter.py
│   ├── models/
│   │   ├── paper.py
│   │   ├── reaction_record.py
│   │   └── ...
│   ├── pipeline/
│   │   ├── load_documents.py           ← Shared input layer (pdfplumber)
│   │   ├── classify_phase.py           ← solution vs solid phase (GPT-4o)
│   │   ├── run_mermaid.py              ← MERMaid orchestration
│   │   ├── run_text_organisation.py    ← Module 2.01 (GPT-4o)
│   │   ├── run_identifier_dictionary.py← Module 2.02 (GPT-4o)
│   │   ├── classify_relevant_figures.py← Module 2.03 (GPT-4o vision)
│   │   ├── run_si_extraction.py        ← Module 2.04 — masses/mmol from SI (GPT-4o)
│   │   ├── run_figure_extraction.py    ← Module 3 — primary extraction (GPT-4o vision)
│   │   ├── validate_and_normalize.py   ← Module 4 — completeness check (GPT-4o)
│   │   ├── fill_missing_fields.py      ← Module 5 — fill gaps (GPT-4o)
│   │   ├── save_outputs.py             ← Module 6 + CSV/Excel export
│   │   ├── run_pipeline.py             ← orchestrator
│   │   └── register_papers.py
│   └── utils/
│       ├── download_papers.py      ← auto-download PDFs via Unpaywall
│       ├── logging_utils.py
│       ├── json_utils.py
│       └── text_utils.py
└── tests/
    ├── test_schema.py
    └── test_pipeline_smoke.py
```

---

## Quick start

### Requirements

- Python 3.9+
- An OpenAI API key (GPT-4o)
- MERMaid installed (VisualHeist + DataRaider) for real figure extraction

### Setup

```bash
git clone https://github.com/shixuanleong/autoglyco.git
cd autoglyco

python -m venv .venv
source .venv/bin/activate       # Windows: .venv\Scripts\activate

pip install -r requirements.txt

cp .env.example .env
# Edit .env and set:
#   OPENAI_API_KEY=sk-...
#   PIPELINE_MODE=real
```

### Add a paper

1. Put the paper PDF in `data/raw/papers/`
2. Add an entry to `data/samples/sample_paper_metadata.json`:

```json
{
  "paper_id": "MY_PAPER_2024",
  "title":    "Paper title",
  "doi":      "10.xxxx/...",
  "year":     2024,
  "pdf_path": "data/raw/papers/my_paper.pdf",
  "si_path":  "data/raw/papers/my_paper_SI.pdf"
}
```

3. Run:

```bash
PIPELINE_MODE=real python -m src.main --paper MY_PAPER_2024
```

The pipeline will auto-detect if the SI PDF is missing and print the exact
download link if it cannot be fetched automatically.

### Mock mode (no API key needed)

```bash
# Leave PIPELINE_MODE=mock in .env (the default)
python -m src.main
```

Uses bundled sample data — useful for testing the pipeline logic without
making any API calls.

---

## Outputs

| File | Description |
|------|-------------|
| `data/outputs/{paper_id}_solution.csv` | Extracted solution-phase reactions, 30 columns |
| `data/outputs/{paper_id}_solid.csv` | Extracted solid-phase reactions, 24 columns |
| `data/outputs/test.xlsx` | Both tabs (Solution + Solid) in one styled Excel file |
| `data/outputs/{paper_id}_schemes.json` | Full structured extraction per figure |
| `data/outputs/{paper_id}_provenance.json` | Source tracking (figure/SI/text) per scheme |
| `data/intermediate/{paper_id}_si_data.json` | Raw SI experimental quantities per compound |

### CSV columns (solution phase)

`DOI`, `Donor_ID`, `Donor_Name`, `Donor_SMILES`, `Donor_Mass_mg`, `Donor_mmol`,
`Acceptor_ID`, `Acceptor_Name`, `Acceptor_SMILES`, `Acceptor_Mass_mg`, `Acceptor_mmol`,
`Equiv.`, `Activator_1`, `Activator_1_Mass_mg`, `Activator_1_mmol`,
`Activator_2`, `Activator_2_Volume_uL`, `Activator_2_mmol`,
`Solvent_Name`, `Solvent_Volume_mL`, `Temperature_1_initial`, `Temperature_final_Celsius`,
`Reaction_Time_min`, `Product_ID`, `Product_Name`, `Product_Mass_mg`,
`a:b_ratio`, `Yield(%)`, `Step`, `Comments`

**Data sources per column:**
- Compound IDs, names, conditions (solvent/temp/time/yield/activator) → extracted from scheme figures via GPT-4o vision
- Masses (mg), mmol, exact volumes → extracted from SI experimental procedures via GPT-4o text
- SMILES → from SI text if explicitly written; otherwise null

---

## Pipeline modules

| Module | File | What it does |
|--------|------|-------------|
| Shared Input | `load_documents.py` | Extract text from PDF + SI with pdfplumber; auto-download missing PDFs |
| Phase classifier | `classify_phase.py` | Classify solution-phase vs solid-phase using GPT-4o |
| MERMaid | `mermaid_adapter.py` | Run VisualHeist (figure → PNG) + DataRaider (PNG → structured JSON) |
| 2.01 Text org | `run_text_organisation.py` | Organise main text into sections (GPT-4o) |
| 2.02 ID dict | `run_identifier_dictionary.py` | Resolve compound labels to names (GPT-4o) |
| 2.03 Fig check | `classify_relevant_figures.py` | Decide which figures are synthesis schemes (GPT-4o vision) |
| 2.04 SI extract | `run_si_extraction.py` | Extract masses/mmol from SI experimental section (GPT-4o) |
| 3 Fig extraction | `run_figure_extraction.py` | Extract donor/acceptor/product/conditions per scheme (GPT-4o vision) |
| 4 Completeness | `validate_and_normalize.py` | Check which fields are missing (GPT-4o) |
| 5 Fill fields | `fill_missing_fields.py` | Fill gaps using text context (GPT-4o) |
| 6 Post-process | `save_outputs.py` | Standardise, track provenance, export CSV + Excel |

---

## Running tests

```bash
pytest tests/ -v
```
