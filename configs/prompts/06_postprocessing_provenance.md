# Module 7: Post-processing & Provenance

## Prompt

```text
You are given a filled reaction extraction JSON. Your task is to clean, standardize, and add provenance information for the final dataset-ready output.

Post-processing tasks:
1. Standardize field names.
2. Keep compound IDs and verified compound names together.
3. Mark each compound as verified, unresolved, or uncertain.
4. Standardize missing values as null.
5. Standardize reaction_type labels.
6. Add source tracking for filled information.
7. Remove duplicated or inconsistent fields.
8. Preserve unresolved fields instead of guessing.
9. Generate a clean final JSON suitable for dataset construction.

Allowed reaction_type labels:
- glycosylation
- protection
- deprotection
- global_deprotection
- other
- unknown

Allowed phase labels:
- solution
- solid
- mixed
- unknown

Allowed compound status labels:
- verified
- unresolved
- uncertain

Rules:
- Do not change chemically meaningful information unless it is only a formatting cleanup.
- Do not replace compound IDs with names only; always keep both.
- If a compound name was added from the dictionary, record the dictionary evidence.
- If a condition was added from SI or main text, record the evidence.
- If information comes only from the figure, source_type should be "figure".
- If no source is available, source_type should be null.

Return only JSON:

{
  "final_output": {
    "phase": "solution",
    "scheme_steps_count": 1,
    "reaction_steps": [
      {
        "step": 1,
        "reaction_type": "glycosylation",
        "donor": {
          "compound_id": "5",
          "compound_name": "Full verified name",
          "status": "verified",
          "source_type": "compound_dictionary",
          "evidence_text": "..."
        },
        "acceptor": {
          "compound_id": "26",
          "compound_name": "Full verified name",
          "status": "verified",
          "source_type": "compound_dictionary",
          "evidence_text": "..."
        },
        "product": {
          "compound_id": "63",
          "compound_name": null,
          "status": "unresolved",
          "source_type": null,
          "evidence_text": null
        },
        "solution_conditions": {
          "donor_smiles": null,
          "donor_mass_mg": null,
          "donor_mmol": null,
          "acceptor_smiles": null,
          "acceptor_mass_mg": null,
          "acceptor_mmol": null,
          "equivalents": null,
          "activator_1_name": "NIS",
          "activator_1_mass_mg": null,
          "activator_1_mmol": null,
          "activator_2_name": "AgOTf",
          "activator_2_volume_uL": null,
          "activator_2_mmol": null,
          "solvent_name": "CH2Cl2",
          "solvent_volume_mL": null,
          "temperature_initial_celsius": "-40",
          "temperature_final_celsius": "-40",
          "reaction_time_min": "10",
          "product_mass_mg": null,
          "a_b_ratio": null,
          "yield_percent": "82%",
          "comments": null,
          "source_type": "SI_experimental_procedure",
          "evidence_text": "..."
        }
      }
    ]
  },
  "provenance_summary": {
    "figure_used": true,
    "main_text_used": true,
    "SI_used": true,
    "compound_dictionary_used": true,
    "manual_check_required": false
  },
  "unresolved_items": []
}
```

## Input

- Filled reaction extraction JSON from `06_Fill Missing Fields`

This input may already contain:

- phase
- scheme step count
- reaction steps
- compound IDs
- verified compound names
- compound status
- reaction conditions
- evidence text
- source type
- unresolved or uncertain fields

## Expected Output

A clean final JSON object suitable for dataset construction.

The output should include:

- `final_output`
- `provenance_summary`
- `unresolved_items`

The final output should contain standardized:

- phase label
- scheme step count
- reaction step objects
- reaction type labels
- compound ID and compound name fields
- compound verification status
- reaction condition fields
- source tracking and evidence text

## Rules / Notes

- Standardize field names.
- Keep compound IDs and verified compound names together.
- Do not replace compound IDs with compound names only.
- Mark each compound as:
  - `verified`
  - `unresolved`
  - `uncertain`
- Standardize missing values as `null`.
- Standardize reaction type labels using only:
  - `glycosylation`
  - `protection`
  - `deprotection`
  - `global_deprotection`
  - `other`
  - `unknown`
- Standardize phase labels using only:
  - `solution`
  - `solid`
  - `mixed`
  - `unknown`
- Add source tracking for filled information.
- If a compound name was added from the compound dictionary, record the dictionary evidence.
- If a condition was added from SI or main text, record the evidence.
- If information comes only from the figure, set `source_type` as `figure`.
- If no source is available, set `source_type` as `null`.
- Remove duplicated or inconsistent fields.
- Preserve unresolved fields instead of guessing.
- Do not change chemically meaningful information unless it is only formatting cleanup.
- Return only JSON.

## Example JSON

```json
{
  "final_output": {
    "phase": "solution",
    "scheme_steps_count": 1,
    "reaction_steps": [
      {
        "step": 1,
        "reaction_type": "glycosylation",
        "donor": {
          "compound_id": "5",
          "compound_name": "Full verified name",
          "status": "verified",
          "source_type": "compound_dictionary",
          "evidence_text": "..."
        },
        "acceptor": {
          "compound_id": "26",
          "compound_name": "Full verified name",
          "status": "verified",
          "source_type": "compound_dictionary",
          "evidence_text": "..."
        },
        "product": {
          "compound_id": "63",
          "compound_name": null,
          "status": "unresolved",
          "source_type": null,
          "evidence_text": null
        },
        "solution_conditions": {
          "donor_smiles": null,
          "donor_mass_mg": null,
          "donor_mmol": null,
          "acceptor_smiles": null,
          "acceptor_mass_mg": null,
          "acceptor_mmol": null,
          "equivalents": null,
          "activator_1_name": "NIS",
          "activator_1_mass_mg": null,
          "activator_1_mmol": null,
          "activator_2_name": "AgOTf",
          "activator_2_volume_uL": null,
          "activator_2_mmol": null,
          "solvent_name": "CH2Cl2",
          "solvent_volume_mL": null,
          "temperature_initial_celsius": "-40",
          "temperature_final_celsius": "-40",
          "reaction_time_min": "10",
          "product_mass_mg": null,
          "a_b_ratio": null,
          "yield_percent": "82%",
          "comments": null,
          "source_type": "SI_experimental_procedure",
          "evidence_text": "..."
        }
      }
    ]
  },
  "provenance_summary": {
    "figure_used": true,
    "main_text_used": true,
    "SI_used": true,
    "compound_dictionary_used": true,
    "manual_check_required": false
  },
  "unresolved_items": []
}
```