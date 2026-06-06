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
Include a compound in Verified compounds when the compound ID and its name appear together in any of the following ways:

Accepted direct-pair formats include:
- Full compound name (ID)
- ID. Full compound name
- Compound ID: Full compound name
- SI section heading "Compound ID" or just the number as a heading, followed by the IUPAC name in the first sentence of the paragraph below it
- Characterization paragraph where the heading is the compound number and the opening sentence contains the compound name (e.g. "9. Methyl 2,3,4-tri-O-acetyl-α-D-glucopyranoside (compound 9) was obtained...")
- Any sentence where a compound number and a chemical name appear in the same sentence or adjacent sentences

Accepted evidence locations include:
- scheme labels
- figure labels
- captions
- reaction annotations
- SI headings/titles
- characterization entries
- experimental subheadings
- NMR data paragraphs (the heading number + the name in the opening line)

Do not:
- infer names from drawn structures
- invent names not present in the text
- expand abbreviations unless explicitly written

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

- Include a compound in `Verified compounds` when its ID and name appear together in any accepted format.
- Accepted direct-pair formats include:
  - `Full compound name (ID)`
  - `ID. Full compound name`
  - `Compound ID: Full compound name`
  - SI section heading that is just the compound number, with the IUPAC name in the first sentence of the paragraph below
  - Any sentence where a compound number and a chemical name appear together
- Accepted evidence locations include:
  - scheme labels
  - figure labels
  - captions
  - reaction annotations
  - SI headings / titles
  - characterization entries
  - experimental subheadings
  - NMR data paragraphs (heading number + name in opening line)
- Do not infer compound names from drawn structures.
- Do not invent names.
- Do not expand abbreviations unless explicitly written.
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