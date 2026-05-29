# Module 3: Synthesis-related Figure Check

## Prompt

```text
You are given a figure image from a carbohydrate chemistry or glycoscience paper.

Your task is to determine whether this figure should enter a pipeline for extracting polysaccharide or glycan synthesis information.

Classify the figure as synthesis-related if it contains one or more of the following:
- a reaction scheme or synthetic route
- compound identifiers connected by reaction arrows
- glycosylation, protection, deprotection, or global deprotection steps
- donor and acceptor transformations
- oligosaccharide or polysaccharide assembly sequences
- automated glycan assembly, solid-phase synthesis, resin-bound intermediates, linkers, or repeated cycles
- reaction conditions, reagents, temperatures, yields, or step labels associated with compound transformations

Classify the figure as not synthesis-related if it mainly contains:
- only isolated molecule structures without reaction arrows or transformations
- biological assay results
- NMR, HPLC, MS, IR, or other spectra
- tables, charts, plots, or statistical graphs
- microscopy or imaging data
- mechanism-only diagrams without an actual synthetic sequence
- general workflow or conceptual diagrams without compound-to-compound synthesis steps

If the figure contains both synthesis information and non-synthesis panels, classify it as synthesis-related as long as at least one panel contains an actual synthetic route or reaction scheme.

Return only valid JSON:

{
  "is_synthesis_related": true,
  "figure_type": "reaction_scheme",
  "confidence": "high",
  "reason": "The figure contains numbered carbohydrate intermediates connected by reaction arrows with reagents and conditions."
}
```

## Input

- Figure image from a carbohydrate chemistry or glycoscience paper

## Expected Output

A valid JSON object indicating:

- whether the figure is synthesis-related
- figure type
- confidence level
- short reason for the classification

## Rules / Notes

- Classify the figure as synthesis-related if it contains reaction schemes, synthetic routes, compound identifiers connected by arrows, glycosylation/protection/deprotection/global deprotection steps, donor/acceptor transformations, oligosaccharide or polysaccharide assembly sequences, AGA schemes, solid-phase synthesis, resin-bound intermediates, linkers, repeated cycles, or reaction conditions associated with compound transformations.
- Classify the figure as not synthesis-related if it mainly contains isolated molecule structures, biological assay results, spectra, tables, charts, plots, microscopy images, mechanism-only diagrams, or general workflow diagrams without compound-to-compound synthesis steps.
- If a multi-panel figure contains both synthesis and non-synthesis panels, classify it as synthesis-related as long as at least one panel contains an actual synthetic route or reaction scheme.
- Return only valid JSON.

## Example JSON

```json
{
  "is_synthesis_related": true,
  "figure_type": "reaction_scheme",
  "confidence": "high",
  "reason": "The figure contains numbered carbohydrate intermediates connected by reaction arrows with reagents and conditions."
}
```