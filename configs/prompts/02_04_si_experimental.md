# Module 2.04: SI Experimental Procedure Extraction

## Purpose

Read the Supporting Information (SI) experimental section and extract
masses, mmol, volumes, SMILES, and other quantities for each compound
mentioned in a list of target product IDs.

Chemistry SI sections have one paragraph per compound, like:

  "Compound 24. Donor 11 (48 mg, 0.12 mmol) and acceptor 21 (35 mg,
   0.10 mmol) were dissolved in dry DCM (2 mL). NIS (54 mg, 0.24 mmol)
   and TfOH (2 µL, 0.023 mmol) were added at −40 °C and the mixture was
   stirred for 2 h. Yield: 78%, α:β = 10:1.
   SMILES: CC1OC(O)..."

## Prompt

```text
You are a chemistry data extraction expert. You are given the Supporting Information (SI) text from a glycosylation chemistry paper. Your task is to find the experimental procedure paragraph for each of the target product compound IDs listed below, and extract the quantities used in that reaction.

Target product IDs:
{PRODUCT_IDS}

For each target product ID, find the paragraph in the SI that describes its synthesis. Then extract:
- donor_id: compound ID of the glycosyl donor (the number/label of the donor compound)
- donor_mass_mg: mass of donor used in mg (number only, no units)
- donor_mmol: mmol of donor used (number only, no units)
- donor_smiles: SMILES string if explicitly written in the text, else null
- acceptor_id: compound ID of the acceptor
- acceptor_mass_mg: mass of acceptor used in mg (number only, no units)
- acceptor_mmol: mmol of acceptor used (number only, no units)
- acceptor_smiles: SMILES string if explicitly written, else null
- activator_1_name: name of primary activator/promoter (e.g. "NIS", "Tf2O")
- activator_1_mass_mg: mass of activator 1 in mg (number only)
- activator_1_mmol: mmol of activator 1 (number only)
- activator_2_name: name of second activator if present (e.g. "TfOH", "AgOTf"), else null
- activator_2_volume_uL: volume of activator 2 in µL if given as liquid (number only), else null
- activator_2_mmol: mmol of activator 2 (number only), else null
- solvent_name: name of solvent (e.g. "DCM", "CH2Cl2", "THF")
- solvent_volume_mL: volume of solvent in mL (number only)
- temperature_initial_celsius: starting temperature as number (e.g. "-40", "0", "25")
- temperature_final_celsius: final/RT temperature if reaction warms up, else same as initial
- reaction_time_min: reaction time converted to minutes (number only)
- product_mass_mg: isolated mass of the product in mg (number only), else null
- yield_percent: yield as written (e.g. "78%", "68")
- a_b_ratio: alpha:beta stereoselectivity ratio as written (e.g. "10:1", "α only"), else null
- product_smiles: SMILES of the product if written, else null
- comments: any notable comments (unusual conditions, notes on selectivity), else null

Rules:
- Only extract data that is explicitly written in the SI text. Do NOT invent or estimate values.
- If a field is not mentioned in the paragraph, return null.
- For compound IDs, use the exact label from the paper (number or alphanumeric code).
- Masses should be numbers only: "48 mg" → "48", not "48 mg".
- Time should be in minutes: "2 h" → "120", "30 min" → "30".
- Temperature should be a number: "−40 °C" → "-40", "rt" or "RT" → "25".
- If the paragraph for a product ID is not found in the SI text, return null for all fields.

Return a JSON object where each key is a product compound ID (as a string) and the value is an object with the fields above:

{
  "24": {
    "donor_id": "11",
    "donor_mass_mg": "48",
    "donor_mmol": "0.12",
    "donor_smiles": null,
    "acceptor_id": "21",
    "acceptor_mass_mg": "35",
    "acceptor_mmol": "0.10",
    "acceptor_smiles": null,
    "activator_1_name": "NIS",
    "activator_1_mass_mg": "54",
    "activator_1_mmol": "0.24",
    "activator_2_name": "TfOH",
    "activator_2_volume_uL": "2",
    "activator_2_mmol": "0.023",
    "solvent_name": "DCM",
    "solvent_volume_mL": "2",
    "temperature_initial_celsius": "-40",
    "temperature_final_celsius": "-40",
    "reaction_time_min": "120",
    "product_mass_mg": "42",
    "yield_percent": "78%",
    "a_b_ratio": "10:1",
    "product_smiles": null,
    "comments": null
  },
  "33": {
    "donor_id": null,
    "donor_mass_mg": null,
    ...
  }
}
```
