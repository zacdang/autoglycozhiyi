# Module 2: SI Organization and Compound Dictionary

## Prompt

```text
You will extract all compound name–ID pairings from a carbohydrate synthesis paper.

Input
- Main Article
- Supporting Information

For each verified compound, extract:
- compound_id
- compound_name
- evidence_text

Verification rule
Include a compound in Verified compounds only when a full compound name is explicitly and directly paired with an ID.

Accepted direct-pair formats include:
- Full compound name (ID)
- ID. Full compound name
- Compound ID: Full compound name

Accepted evidence locations include:
- scheme labels
- figure labels
- captions
- reaction annotations
- SI headings/titles
- characterization entries
- experimental subheadings

Do not:
- infer from structures
- invent names
- expand abbreviations unless explicitly written
- treat a numbered intermediate as verified without a direct full name–ID pairing

Sorting
Sort Verified compounds by compound_id:
- S-prefixed IDs first in ascending natural order
- then numeric IDs in ascending numeric order

Evidence
- Keep evidence_text short
- Prefer SI title/header evidence when available

Procedure
1. Collect all mentioned IDs from the Main Article and Supporting Information.
2. Verify each ID against direct name–ID evidence.
3. Re-check unresolved IDs once.
4. For continuous or near-continuous numbering series, do one extra targeted SI re-check.
5. Any mentioned ID still lacking a direct full name–ID pairing goes in Unresolved mentions.

For every unresolved mention, explain briefly why it could not be verified as a compound name–ID pairing.

Use a short simple reason, such as:
- no direct full name–ID pairing found
- only the compound ID was mentioned
- only a structure was shown
- only an abbreviated or partial name was given
- the full name and ID appeared separately but were not directly paired

Keep the reason short and specific.

Output
Return exactly two sections:

Verified compounds

ID: 7
Name: full compound name exactly as supported by the text
Evidence: "Short supporting snippet."

Unresolved mentions

ID: 2
Reason: only the compound ID was mentioned
Evidence: "Short supporting snippet."

ID: 5
Reason: no direct full name–ID pairing found
Evidence: "Short supporting snippet."

If there are none, write:

Unresolved mentions

None
```

## Input

- Main Article
- Supporting Information

## Expected Output

Two output sections:

1. `Verified compounds`

For each verified compound, include:

- compound ID
- full compound name
- short evidence text

2. `Unresolved mentions`

For mentioned IDs that cannot be verified as direct compound name–ID pairings, include:

- compound ID
- short reason
- short evidence text

## Rules / Notes

- Include a compound in `Verified compounds` only when a full compound name is explicitly and directly paired with an ID.
- Accepted direct-pair formats include:
  - `Full compound name (ID)`
  - `ID. Full compound name`
  - `Compound ID: Full compound name`
- Accepted evidence locations include:
  - scheme labels
  - figure labels
  - captions
  - reaction annotations
  - SI headings / titles
  - characterization entries
  - experimental subheadings
- Do not infer compound names from structures.
- Do not invent names.
- Do not expand abbreviations unless explicitly written.
- Do not treat a numbered intermediate as verified without a direct full name–ID pairing.
- Keep evidence text short.
- Prefer SI title / header evidence when available.
- Sort verified compounds by compound ID:
  - S-prefixed IDs first in ascending natural order
  - numeric IDs second in ascending numeric order
- Put all mentioned but unverified IDs under `Unresolved mentions`.
- For unresolved mentions, give a short and specific reason.

## Example JSON

```json
{
  "verified_compounds": [
    {
      "compound_id": "S3",
      "compound_name": "full compound name exactly as supported by the text",
      "evidence_text": "S3. Full compound name..."
    },
    {
      "compound_id": "7",
      "compound_name": "full compound name exactly as supported by the text",
      "evidence_text": "Compound 7: full compound name..."
    }
  ],
  "unresolved_mentions": [
    {
      "compound_id": "2",
      "reason": "only the compound ID was mentioned",
      "evidence_text": "Compound 2 was used..."
    },
    {
      "compound_id": "5",
      "reason": "no direct full name–ID pairing found",
      "evidence_text": "5"
    }
  ]
}
```