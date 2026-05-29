# Module 5: Completeness Check

## Prompt

```text
You are given a structured JSON output extracted from a reaction scheme. Your task is to check whether the output is complete enough for downstream dataset construction.

Check the following fields:

Scheme-level fields:
- phase
- scheme_steps_count
- reaction_paths, if the scheme is multi-step or branched
- final_product or terminal products

Step-level fields:
- step number
- reaction_type
- from_compound or reactant/predecessor
- product
- donor, only for glycosylation steps
- acceptor, only for glycosylation steps
- reaction conditions, if visible or provided in text
- yield, if available
- stereoselectivity, if available

Rules:
- For glycosylation steps, donor and acceptor should be checked.
- For protection, deprotection, and global deprotection steps, donor and acceptor are not required.
- If a field is absent because it is not provided in the source, mark it as "not_available", not as an error.
- If a field should be present but was missed, mark it as "missing".
- If a field is uncertain, mark it as "uncertain".
- Do not invent missing information.
- Suggest whether the missing field should be filled from the figure, main text, SI, compound dictionary, or manual check.

Return only JSON:

{
  "is_complete": false,
  "overall_status": "partially_complete",
  "missing_or_uncertain_fields": [
    {
      "level": "step",
      "step": 1,
      "field": "acceptor",
      "status": "missing",
      "reason": "The step is classified as glycosylation, but no acceptor was identified.",
      "recommended_source_to_check": "figure_and_text"
    },
    {
      "level": "step",
      "step": 2,
      "field": "temperature",
      "status": "not_available",
      "reason": "Temperature was not reported in the provided figure or text.",
      "recommended_source_to_check": "none"
    }
  ],
  "fields_ready_for_post_processing": [
    "compound_id",
    "reaction_type",
    "product"
  ],
  "fields_need_filling": [
    "compound_name",
    "reaction_conditions"
  ],
  "manual_check_required": true
}
```

## Input

- Structured JSON output extracted from a reaction scheme

Usually this input comes from:

- `04_Primary Figure-based Extraction`
- optional related text evidence from `01_Text Organisation`
- optional compound dictionary from `02_Identifier Dictionary Builder`

## Expected Output

A JSON object that reports whether the extracted scheme output is complete enough for downstream dataset construction.

The output should include:

- `is_complete`
- `overall_status`
- `missing_or_uncertain_fields`
- `fields_ready_for_post_processing`
- `fields_need_filling`
- `manual_check_required`

## Rules / Notes

- Check both scheme-level and step-level fields.
- Scheme-level fields include:
  - `phase`
  - `scheme_steps_count`
  - `reaction_paths`, if the scheme is multi-step or branched
  - final product or terminal products
- Step-level fields include:
  - step number
  - reaction type
  - from compound / reactant / predecessor
  - product
  - donor, only for glycosylation steps
  - acceptor, only for glycosylation steps
  - reaction conditions, if visible or provided in text
  - yield, if available
  - stereoselectivity, if available
- For glycosylation steps, donor and acceptor should be checked.
- For protection, deprotection, and global deprotection steps, donor and acceptor are not required.
- If a field is absent because it is not provided in the source, mark it as `not_available`, not as an error.
- If a field should be present but was missed, mark it as `missing`.
- If a field is uncertain, mark it as `uncertain`.
- Do not invent missing information.
- Recommend where the missing or uncertain field should be checked:
  - figure
  - main text
  - SI
  - compound dictionary
  - manual check
  - none
- Return only JSON.

## Example JSON

```json
{
  "is_complete": false,
  "overall_status": "partially_complete",
  "missing_or_uncertain_fields": [
    {
      "level": "step",
      "step": 1,
      "field": "acceptor",
      "status": "missing",
      "reason": "The step is classified as glycosylation, but no acceptor was identified.",
      "recommended_source_to_check": "figure_and_text"
    },
    {
      "level": "step",
      "step": 2,
      "field": "temperature",
      "status": "not_available",
      "reason": "Temperature was not reported in the provided figure or text.",
      "recommended_source_to_check": "none"
    }
  ],
  "fields_ready_for_post_processing": [
    "compound_id",
    "reaction_type",
    "product"
  ],
  "fields_need_filling": [
    "compound_name",
    "reaction_conditions"
  ],
  "manual_check_required": true
}
```