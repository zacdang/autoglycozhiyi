# Module 1: Text Organization

## Prompt

```text
You are given the extracted text from a carbohydrate synthesis paper, including the Main Article and Supporting Information.

Your task is to organise the text into structured evidence blocks for downstream reaction scheme extraction.

The goal is NOT to summarize the paper.
The goal is to classify and preserve useful text evidence so that later modules can use it to fill missing fields such as compound names, procedure references, reagents, solvents, temperature, time, yield, stereoselectivity, and other reaction details.

Input:
1. Main Article text
2. Supporting Information text

Task:

Organise the text into the following evidence categories:

1. figure_captions
Text that describes figures, schemes, reaction routes, synthetic schemes, or tables.
Include figure numbers, scheme numbers, captions, and nearby explanatory text when clearly connected.

2. synthesis_procedures
Text describing specific synthetic reactions or preparation of compounds.
This includes:
- procedure titles
- compound preparation entries
- reaction operations
- donor or acceptor usage
- reagents
- solvents
- temperature
- reaction time
- purification
- yield
- stereoselectivity
- product identity

3. general_procedures
Text describing reusable procedures, such as Procedure A, Procedure B, General glycosylation procedure, General deprotection procedure, or automated glycan assembly cycles.
These procedures may be referenced later by compound-specific entries.

4. compound_characterization
Text mainly reporting characterization data for compounds.
This includes:
- NMR data
- HRMS data
- MS data
- optical rotation
- IR data
- analytical data
- compound headings or compound titles

Important:
If a compound characterization entry contains a direct compound name–ID pairing in the heading or title, preserve that heading carefully because it may be useful for compound dictionary construction.

5. tables
Text from tables or table captions that may contain synthesis-relevant information.
Include tables only if they contain reaction conditions, donor/acceptor information, yields, stereoselectivity, compound IDs, or procedure references.

6. irrelevant_text
Text that is not useful for synthesis extraction.
This may include:
- introduction background
- biological assay discussion
- long discussion unrelated to synthesis
- references
- acknowledgements
- spectra-only pages without useful compound headings
- instrument-only descriptions
- unrelated figures or statistical results

Rules:

1. Preserve evidence text.
Do not rewrite chemical names, compound IDs, reagents, solvents, temperatures, yields, or procedure labels.

2. Do not invent missing information.
Only use text explicitly present in the Main Article or Supporting Information.

3. Do not infer compound names from structures.

4. Do not expand abbreviations unless the full form is explicitly written.

5. Keep each evidence block short but complete enough to support later extraction.

6. If one text block belongs to multiple categories, assign it to the most useful category for downstream synthesis extraction.
For example:
- A compound heading with NMR data should go under compound_characterization.
- A reaction paragraph with yield and product formation should go under synthesis_procedures.
- A reusable Procedure B description should go under general_procedures.
- A scheme caption should go under figure_captions.

7. Preserve source location if available.
Use labels such as:
- Main Article
- Supporting Information
- Figure caption
- Scheme caption
- General Procedure
- Compound entry
- Table

8. If figure or scheme numbers are mentioned, preserve them exactly.
For example:
- Scheme 1
- Figure 2
- Fig. S3
- Table S1

9. If a procedure reference is mentioned, preserve it exactly.
For example:
- Procedure A
- General procedure B
- Method C
- Automated glycan assembly cycle

10. If a compound ID appears, preserve it exactly.
Do not normalize IDs.
Examples:
- 5
- 26
- S3
- BB1
- BB1*
- L1
- SP

Output:

Return valid JSON only.

Use this exact structure:

{
  "text_organisation": {
    "figure_captions": [
      {
        "source_type": "Main Article | Supporting Information",
        "label": "Scheme 1 | Figure 2 | Table S1 | null",
        "evidence_text": "Short preserved text block.",
        "relevance": "reaction_scheme | synthesis_route | table_conditions | compound_mapping | other"
      }
    ],
    "synthesis_procedures": [
      {
        "source_type": "Main Article | Supporting Information",
        "procedure_label": "Procedure A | General procedure B | null",
        "compound_ids_mentioned": ["5", "26"],
        "evidence_text": "Short preserved text block.",
        "extracted_cues": {
          "compound_names": ["explicit compound names if present"],
          "reagents": ["explicit reagents if present"],
          "solvents": ["explicit solvents if present"],
          "temperature": "explicit temperature if present or null",
          "time": "explicit time if present or null",
          "yield": "explicit yield if present or null",
          "stereoselectivity": "explicit stereoselectivity if present or null"
        }
      }
    ],
    "general_procedures": [
      {
        "source_type": "Main Article | Supporting Information",
        "procedure_label": "Procedure A | General procedure B | null",
        "procedure_type": "glycosylation | protection | deprotection | global_deprotection | cleavage | AGA_cycle | unknown",
        "evidence_text": "Short preserved text block.",
        "extracted_cues": {
          "reagents": ["explicit reagents if present"],
          "solvents": ["explicit solvents if present"],
          "temperature": "explicit temperature if present or null",
          "time": "explicit time if present or null",
          "cycle_or_stage_clue": "explicit cycle/stage clue if present or null"
        }
      }
    ],
    "compound_characterization": [
      {
        "source_type": "Supporting Information | Main Article",
        "compound_id": "compound ID if directly shown or null",
        "compound_name": "full compound name if directly paired with ID or null",
        "evidence_text": "Short preserved heading or characterization entry.",
        "contains_direct_name_id_pairing": true
      }
    ],
    "tables": [
      {
        "source_type": "Main Article | Supporting Information",
        "table_label": "Table 1 | Table S1 | null",
        "evidence_text": "Short preserved table text or caption.",
        "relevance": "reaction_conditions | yields | stereoselectivity | compound_mapping | not_relevant"
      }
    ],
    "irrelevant_text": [
      {
        "source_type": "Main Article | Supporting Information",
        "reason": "background | biological_assay | spectra_only | references | acknowledgements | unrelated_discussion | other",
        "evidence_text": "Short text snippet or section label."
      }
    ]
  },
  "organisation_summary": {
    "main_article_used": true,
    "supporting_information_used": true,
    "figure_captions_found": true,
    "synthesis_procedures_found": true,
    "general_procedures_found": true,
    "compound_characterization_found": true,
    "tables_found": true,
    "notes": "One short sentence describing the usefulness of the organised text for downstream extraction."
  }
}
```

## Input

- Main Article text
- Supporting Information text

## Expected Output

A structured JSON object that organises the extracted text into evidence blocks, including:

- `figure_captions`
- `synthesis_procedures`
- `general_procedures`
- `compound_characterization`
- `tables`
- `irrelevant_text`
- `organisation_summary`

## Rules / Notes

- This module is used for text organisation, not paper summarisation.
- Preserve useful text evidence for downstream reaction scheme extraction.
- Do not rewrite chemical names, compound IDs, reagents, solvents, temperatures, yields, procedure labels, or stereoselectivity information.
- Do not invent missing information.
- Do not infer compound names from structures.
- Do not expand abbreviations unless the full form is explicitly written.
- Keep each evidence block short but complete enough to support later extraction.
- Preserve source location when available.
- Preserve figure, scheme, table, procedure, and compound IDs exactly.
- If one text block belongs to multiple categories, assign it to the category most useful for downstream synthesis extraction.

## Example JSON

```json
{
  "text_organisation": {
    "figure_captions": [
      {
        "source_type": "Main Article",
        "label": "Scheme 1",
        "evidence_text": "Scheme 1. Synthesis of target oligosaccharide...",
        "relevance": "reaction_scheme"
      }
    ],
    "synthesis_procedures": [
      {
        "source_type": "Supporting Information",
        "procedure_label": "Procedure A",
        "compound_ids_mentioned": ["5", "26"],
        "evidence_text": "Compound 26 was prepared from compound 5 using Procedure A...",
        "extracted_cues": {
          "compound_names": [],
          "reagents": ["explicit reagent if present"],
          "solvents": ["explicit solvent if present"],
          "temperature": "explicit temperature if present or null",
          "time": "explicit time if present or null",
          "yield": "explicit yield if present or null",
          "stereoselectivity": "explicit stereoselectivity if present or null"
        }
      }
    ],
    "general_procedures": [
      {
        "source_type": "Supporting Information",
        "procedure_label": "General glycosylation procedure",
        "procedure_type": "glycosylation",
        "evidence_text": "General glycosylation procedure...",
        "extracted_cues": {
          "reagents": ["explicit reagent if present"],
          "solvents": ["explicit solvent if present"],
          "temperature": "explicit temperature if present or null",
          "time": "explicit time if present or null",
          "cycle_or_stage_clue": null
        }
      }
    ],
    "compound_characterization": [
      {
        "source_type": "Supporting Information",
        "compound_id": "26",
        "compound_name": "full compound name if directly paired with ID",
        "evidence_text": "Compound 26: full compound name...",
        "contains_direct_name_id_pairing": true
      }
    ],
    "tables": [
      {
        "source_type": "Main Article",
        "table_label": "Table 1",
        "evidence_text": "Table 1. Optimization of glycosylation conditions...",
        "relevance": "reaction_conditions"
      }
    ],
    "irrelevant_text": [
      {
        "source_type": "Main Article",
        "reason": "background",
        "evidence_text": "General introduction text not directly useful for synthesis extraction."
      }
    ]
  },
  "organisation_summary": {
    "main_article_used": true,
    "supporting_information_used": true,
    "figure_captions_found": true,
    "synthesis_procedures_found": true,
    "general_procedures_found": true,
    "compound_characterization_found": true,
    "tables_found": true,
    "notes": "The organised text provides supporting evidence for compound names, reaction conditions, procedure references, and scheme interpretation."
  }
}
```