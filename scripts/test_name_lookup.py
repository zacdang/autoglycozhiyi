"""
Quick test for the id_dict name lookup fix in save_outputs.

Loads existing intermediate data from disk and re-runs save_outputs
without making any API calls. Takes ~5 seconds.

Usage:
    python scripts/test_name_lookup.py
"""

import json
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parents[1]))

PAPER_ID   = "SIANTURI_2024"
DATA_DIR   = Path(__file__).parents[1] / "data"
INTER_DIR  = DATA_DIR / "intermediate"
OUTPUT_DIR = DATA_DIR / "outputs"


def load_json(path):
    with open(path) as f:
        return json.load(f)


def main():
    # Load existing schemes
    schemes_path = OUTPUT_DIR / f"{PAPER_ID}_schemes.json"
    schemes_data = load_json(schemes_path)
    scheme_list  = schemes_data.get("schemes", [])
    print(f"Loaded {len(scheme_list)} schemes from {schemes_path.name}")

    # Load SI data
    si_data_path = INTER_DIR / f"{PAPER_ID}_si_data.json"
    si_data = load_json(si_data_path) if si_data_path.exists() else {}
    print(f"SI data: {len(si_data)} compounds")

    # Load completeness reports
    completeness_path = INTER_DIR / f"{PAPER_ID}_completeness.json"
    completeness = load_json(completeness_path) if completeness_path.exists() else []

    # Build a mock id_dict with some known Sianturi 2024 compound names
    # These will be used to test the fallback lookup
    mock_resolved = {
        "9":  {"compound_id": "9",  "compound_name": "Trichloroacetimidate donor 9",  "possible_name": "Trichloroacetimidate donor 9"},
        "10": {"compound_id": "10", "compound_name": "Thioglycoside donor 10",        "possible_name": "Thioglycoside donor 10"},
        "18": {"compound_id": "18", "compound_name": "Lactosamine acceptor 18",       "possible_name": "Lactosamine acceptor 18"},
        "19": {"compound_id": "19", "compound_name": "GlcNAc acceptor 19",            "possible_name": "GlcNAc acceptor 19"},
        "43": {"compound_id": "43", "compound_name": "Linker acceptor 43",            "possible_name": "Linker acceptor 43"},
        "51": {"compound_id": "51", "compound_name": "Diol acceptor 51",              "possible_name": "Diol acceptor 51"},
    }
    id_dict = {"resolved": mock_resolved, "unresolved": {}}
    print(f"Mock id_dict: {len(mock_resolved)} entries")

    # Re-run save_outputs with the patched code
    from src.pipeline.save_outputs import post_process_and_save

    saved = post_process_and_save(
        paper_id             = PAPER_ID,
        fill_results         = scheme_list,   # schemes double as fill_results here
        scheme_extractions   = scheme_list,
        completeness_reports = completeness,
        unified              = {},
        id_dict              = id_dict,
        doi                  = "10.1002/anie.202419516",
        si_data              = si_data,
    )
    print(f"\nSaved files: {list(saved.keys())}")

    # Check the CSV for names
    import pandas as pd
    sol_csv = OUTPUT_DIR / f"{PAPER_ID}_solution.csv"
    if sol_csv.exists():
        df = pd.read_csv(sol_csv)
        print(f"\nSolution CSV: {len(df)} rows")
        name_cols = ["Donor_Name", "Acceptor_Name", "Product_Name"]
        for col in name_cols:
            if col in df.columns:
                filled = df[col].notna() & (df[col] != "")
                print(f"  {col}: {filled.sum()}/{len(df)} filled")
                # Show a sample
                sample = df[df[col].notna() & (df[col] != "")][col].head(3).tolist()
                if sample:
                    print(f"    e.g. {sample}")


if __name__ == "__main__":
    main()
