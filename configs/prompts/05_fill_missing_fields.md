# Module 6: Fill Missing Fields

## Prompt

```text
You are given:
1. A preliminary reaction extraction JSON from a reaction scheme.
2. Organized text evidence from the main text and/or supporting information.
3. A compound identifier dictionary, if available.
4. A completeness check report listing missing or uncertain fields.

Your task is to fill missing or uncertain fields only when there is explicit evidence in the provided text or dictionary.

Priority order for filling information:
1. Use the reaction scheme image extraction if the information is visually clear.
2. Use figure caption or nearby main text.
3. Use experimental procedure or SI.
4. Use compound identifier dictionary for compound full names.
5. If no explicit evidence exists, keep the field as null or unresolved.

Rules:
- Do not infer compound names from chemical structures.
- Do not invent reaction conditions.
- Do not fill donor or acceptor unless there is enough evidence from the scheme or text.
- Keep the original compound ID even after adding a full name.
- Every filled field must include evidence_text and source_type.
- If multiple sources conflict, prioritize the figure for structural sequence and the SI/main text for experimental conditions.
- If still uncertain, mark the field as "uncertain" and explain why.

Return only JSON:

{
  "filled_output": {
    "phase": "solution",
    "reaction_steps": [
      {
        "step": 1,
        "reaction_type": "glycosylation",
        "donor": {
          "compound_id": "5",
          "compound_name": "Full compound name if verified",
          "status": "verified",
          "evidence_text": "Compound 5 was described as ...",
          "source_type": "compound_dictionary"
        },
        "acceptor": {
          "compound_id": "26",
          "compound_name": "Full compound name if verified",
          "status": "verified",
          "evidence_text": "Acceptor 26 was used in the glycosylation...",
          "source_type": "SI_experimental_procedure"
        },
        "product": {
          "compound_id": "63",
          "compound_name": null,
          "status": "unresolved",
          "reason": "No verified full name was found in the provided text."
        },
        "solution_conditions": {
          "solvent": "CH2Cl2",
          "temperature": "-40 °C",
          "time": "10 min",
          "promoter_or_activator": "NIS, AgOTf",
          "yield": "82%",
          "evidence_text": "The reaction was performed in CH2Cl2 at -40 °C using NIS and AgOTf...",
          "source_type": "SI_experimental_procedure"
        }
      }
    ]
  },
  "unfilled_fields": [
    {
      "field": "stereoselectivity",
      "reason": "No explicit stereoselectivity value was provided."
    }
  ]
}
```

## Input

- Preliminary reaction extraction JSON from `04_Primary Figure-based Extraction`
- Organized text evidence from `01_Text Organisation`
- Compound identifier dictionary from `02_Identifier Dictionary Builder`, if available
- Completeness check report from `05_Completeness Check`

## Expected Output

A JSON object containing:

- `filled_output`: the updated reaction extraction output after filling fields with explicit evidence
- `unfilled_fields`: fields that remain null, unresolved, or uncertain because no explicit evidence was found

For each filled field, the output should include:

- filled value
- evidence text
- source type
- verification status where relevant

## Rules / Notes

- Fill missing or uncertain fields only when explicit evidence is available.
- Do not infer compound names from chemical structures.
- Do not invent reaction conditions.
- Do not fill donor or acceptor unless there is enough evidence from the scheme or text.
- Keep the original compound ID even after adding a full compound name.
- Every filled field must include `evidence_text` and `source_type`.
- If multiple sources conflict, prioritize:
  - figure / scheme image for structural sequence
  - SI or main text for experimental conditions
- If no explicit evidence exists, keep the field as `null`, `unresolved`, or `uncertain`.
- Use the compound identifier dictionary only for verified compound full names.
- Return only JSON.

## Example JSON

```json
{
  "filled_output": {
    "phase": "solution",
    "reaction_steps": [
      {
        "step": 1,
        "reaction_type": "glycosylation",
        "donor": {
          "compound_id": "5",
          "compound_name": "Full compound name if verified",
          "status": "verified",
          "evidence_text": "Compound 5 was described as ...",
          "source_type": "compound_dictionary"
        },
        "acceptor": {
          "compound_id": "26",
          "compound_name": "Full compound name if verified",
          "status": "verified",
          "evidence_text": "Acceptor 26 was used in the glycosylation...",
          "source_type": "SI_experimental_procedure"
        },
        "product": {
          "compound_id": "63",
          "compound_name": null,
          "status": "unresolved",
          "reason": "No verified full name was found in the provided text."
        },
        "solution_conditions": {
          "solvent": "CH2Cl2",
          "temperature": "-40 °C",
          "time": "10 min",
          "promoter_or_activator": "NIS, AgOTf",
          "yield": "82%",
          "evidence_text": "The reaction was performed in CH2Cl2 at -40 °C using NIS and AgOTf...",
          "source_type": "SI_experimental_procedure"
        }
      }
    ]
  },
  "unfilled_fields": [
    {
      "field": "stereoselectivity",
      "reason": "No explicit stereoselectivity value was provided."
    }
  ]
}
```