# Module 4: Primary Figure-based Extraction

## Prompt

```text
You will perform TWO tasks on the same carbohydrate synthesis scheme, using the TWO original instruction sets below exactly as written.

Use the same inputs for both tasks:
1) One reaction scheme image (PNG).
2) One reaction description file (TXT).

Do not modify, simplify, reinterpret, or merge the internal rules of either instruction set.
Apply Instruction Set 1 exactly as written to produce the reaction path output.
Apply Instruction Set 2 exactly as written to produce the step analysis output.

Final output requirement:
- Return valid pretty-printed JSON only.
- Combine the two task outputs into this exact top-level structure:
{
  "reaction_paths": [...],
  "step_analysis": {
    "phase": "solution | solid",
    "scheme_steps_count": integer,
    "reaction_steps": [...],
    "notes": "..."
  }
}

Specifically:
- The value of "reaction_paths" must be exactly the array produced by Instruction Set 1.
- The value of "step_analysis" must be exactly the full JSON object produced by Instruction Set 2, except nested under the key "step_analysis".
- Do not change the internal schema of either task output.
- Do not add extra keys.
- Do not omit any keys required by either instruction set.

Instruction Set 1 (apply exactly as written):

You are going to extract terminal-product construction paths from a carbohydrate synthesis scheme.

Use both the scheme image and the reaction description/legend.

Source priority:
- The scheme image is primary for route topology: compound nodes, arrows, branch structure, and terminal product identity.
- The legend is secondary and may be used only to recover an explicit labeled reactant assigned to a specific arrow when that reactant is not redrawn in the scheme.
- Never use the legend to invent extra route nodes.
- If image and legend conflict, use the image for connectivity and use the legend only for explicit labeled reactants assigned to that step.

Task:
For each terminal product, output exactly one stepwise construction path that follows the drawn arrows in order.

Path rules:
- Keep every explicit numbered compound that appears on the route.
- Preserve every drawn reaction arrow as its own "->" step.
- If a drawn step passes through a product/intermediate that has no explicit compound ID, insert a placeholder node:
  [unlabeled_intermediate_1], [unlabeled_intermediate_2], ...
- These placeholders are only positional markers for unlabeled drawn intermediates, not invented chemical species.
- If the same unlabeled intermediate is the product of one step and the starting point of the next, reuse the same placeholder.

External reactant rules:
- Use "+" only for same-step inputs.
- If the legend explicitly assigns a labeled external reactant to a specific arrow, attach it only to that step.
- Format each such step as:
  nodeA + external_id -> nodeB
- If multiple explicit labeled external reactants are assigned to the same step, include them in step order before the arrow.
- Repeat the same external reactant each time it is used on different steps.
- Do not deduplicate repeated uses across the route.

Do not:
- Do not collapse a multistep route into one overall reaction.
- Do not omit explicit numbered on-path intermediates.
- Do not convert drawn numbered intermediates into external reactants.
- Do not invent chemical identities for unlabeled intermediates.
- Do not create extra route nodes beyond explicit numbered nodes and required unlabeled-intermediate placeholders.
- Do not include reagents/conditions that are not explicit compound IDs.
- Do not include failed, crossed-out, or abandoned branches.

Output:
- Return valid pretty-printed JSON only.
- Each terminal product gets one path string.

Return format:
{
  "reaction_paths": [
    {
      "path": "node1 + ext1 -> [unlabeled_intermediate_1] -> node2 + ext2 -> [unlabeled_intermediate_2] -> terminal"
    }
  ]
}

Instruction Set 2 (apply exactly as written):

You are analyzing carbohydrate synthesis reaction schemes to extract structured synthesis knowledge.

Input:
1) One reaction scheme image (PNG).
2) One reaction description file (TXT).
Use BOTH sources. If conflicts occur, rely primarily on the scheme image.

Task:

1) Phase Determination
Decide whether the synthesis is:
solution: stepwise reactions with isolated intermediates
solid: presence of resin beads, linkers (e.g., L1, SP, L), or automated glycan assembly (AGA) cycles

2) Reaction Step Identification
Identify reaction steps STRICTLY in the visual order of arrows or numbered stages.

Allowed reaction_type labels ONLY:
a) glycosylation
b) protection
c) deprotection
d) global_deprotection
e) null

Definitions:
- glycosylation: formation of a glycosidic bond at the anomeric center (C–O or C–N)
- protection: installation of protecting groups without glycosidic bond formation
- deprotection: selective removal of temporary protecting groups followed by further synthesis
- global_deprotection: final removal of permanent protecting groups with no further glycosylation
- null: reagent-only or condition-only transformations

3) Step Expansion Rules
- Each arrow or stage corresponds to EXACTLY one step.
- Repeated building blocks (e.g., “BB1 ×6”) MUST be expanded into that many steps.
- Steps MUST NOT be merged.
- Step indices MUST start from 1 and be consecutive.
- scheme_steps_count MUST equal the expanded total.
- Reagent-only arrows MUST be counted as null steps.

4) Detail Extraction Scope
- First identify reaction_type for every step.
- ONLY glycosylation steps require detailed extraction.
- If reaction_type = glycosylation, continue with donor / acceptor / product assignment and phase-specific condition extraction.
- If reaction_type = protection, deprotection, global_deprotection, or null, STOP after reaction_type identification.
- For non-glycosylation steps, do NOT extract donor, acceptor, product, or any condition fields.
- For non-glycosylation steps, the output object must contain only:
  - step
  - reaction_type

5) Donor / Acceptor / Product Assignment (Glycosylation Steps Only)

5a) Phase Enforcement
If phase = solid → apply ONLY solid-phase rules.
If phase = solution → apply ONLY solution-phase rules.

5b) Solid-Phase Rules (priority order)

i) If specific acceptor identifiers are explicitly shown (e.g., L1, SP, L, BB1*), use them EXACTLY.

ii) For iterative solid-phase synthesis, represent acceptor as cumulative chain:
BBn*-BB(n−1)*-…-L1

Rules:
- Each glycosylation includes implicit deprotection.
- From second glycosylation onward, prepend BBn* to LEFT.
- Preserve order: non-reducing end (left) → support (right).
- Use "-" separator.
- NEVER simplify or reorder.

iii) If none apply:
acceptor = "solid-supported growing glycan"

Donor:
- Must be the incoming glycosyl building block.

Product:
- Must be the resulting labeled chain or product ID.

5c) Solution-Phase Rules

- Donor and acceptor MUST be reactant IDs adjacent to arrow.
- NEVER use product ID as donor or acceptor.
- If OH highlighted → that reactant is acceptor.
- If TXT provides full compound name or SMILES → use verbatim.
- If neither ID nor description exists → donor = null, acceptor = null.

Product:
- Must be labeled product ID after arrow.
- If absent → product = null.

6) Condition Extraction (Glycosylation Steps Only, Phase-Specific)

6a) General Rule
- Extract conditions ONLY for glycosylation steps.
- Extract ONLY information explicitly present in the scheme image and/or TXT.
- DO NOT invent missing conditions.
- If a field is not explicitly given, set it to null.
- Apply ONLY the condition schema that matches the detected phase.
- DO NOT output condition fields from the other phase.

6b) If phase = solution
For each glycosylation step, extract solution-phase reaction conditions when explicitly available:
- solvent
- temperature
- time
- promoter_or_activator
- other_reagents
- equivalents
- yield
- stereoselectivity

Rules:
- These fields describe reaction-specific experimental conditions.
- Prefer conditions directly associated with the current arrow or numbered stage.
- If TXT supplies missing condition details for the same visual step, include them.
- Do NOT include resin-, linker-, or cycle-only clues as solution conditions unless they are explicitly written as reagents/conditions for that step.

6c) If phase = solid
For each glycosylation step, extract ONLY solid-phase-relevant explicitly shown information:
- support_or_linker
- cycle_or_stage_clue
- explicit_reagents
- explicit_solvent
- explicit_temperature
- explicit_time
- cleavage_or_global_deprotection_condition

Rules:
- Solid-phase schemes often do NOT provide full solution-style reaction conditions.
- Therefore, DO NOT assume solvent, temperature, time, promoter, or equivalents unless explicitly shown.
- Prioritize donor, acceptor, linker/support identity, cycle information, and explicitly written operation clues.
- If no explicit condition is shown for a solid-phase glycosylation step, keep all solid-phase condition fields null.

7) Compound Identity Consistency

- Preserve exact identifiers.
- DO NOT normalize names.
- DO NOT remove symbols (e.g., "*").
- DO NOT merge compound identities across steps.
- If the same compound appears under different textual expressions, treat them as the SAME entity if scheme ID matches.

8) Multi-Step Reaction Topology Awareness

- Reaction order MUST follow visual scheme layout.
- Parallel branches MUST be treated as independent paths.
- If product of step A is used in step B → this implies sequence A → B.
- Do NOT infer hidden steps or mechanisms.

9) Grounding Awareness

- If full molecular names appear in TXT, associate them with corresponding scheme IDs.
- If multiple naming forms exist, preserve the most explicit version.
- Maintain consistent compound identity across all steps.

10) Output Format (STRICT)

Output JSON ONLY.
Use normal pretty-printed JSON with indentation.

Top-level schema:
{
  "phase": "solution | solid",
  "scheme_steps_count": integer,
  "reaction_steps": [...],
  "notes": "one short sentence explaining phase determination based on visual or textual cues"
}

Use EXACTLY ONE of the following phase-specific step schemas.

A) If phase = solution

- For glycosylation steps:
{
  "step": integer,
  "reaction_type": "glycosylation",
  "donor": "string | null",
  "acceptor": "string | null",
  "product": "string | null",
  "solution_conditions": {
    "solvent": "string | null",
    "temperature": "string | null",
    "time": "string | null",
    "promoter_or_activator": "string | null",
    "other_reagents": "string | null",
    "equivalents": "string | null",
    "yield": "string | null",
    "stereoselectivity": "string | null"
  }
}

- For protection, deprotection, global_deprotection, or null steps:
{
  "step": integer,
  "reaction_type": "protection | deprotection | global_deprotection | null"
}

B) If phase = solid

- For glycosylation steps:
{
  "step": integer,
  "reaction_type": "glycosylation",
  "donor": "string | null",
  "acceptor": "string | null",
  "product": "string | null",
  "solid_conditions": {
    "support_or_linker": "string | null",
    "cycle_or_stage_clue": "string | null",
    "explicit_reagents": "string | null",
    "explicit_solvent": "string | null",
    "explicit_temperature": "string | null",
    "explicit_time": "string | null",
    "cleavage_or_global_deprotection_condition": "string | null"
  }
}

- For protection, deprotection, global_deprotection, or null steps:
{
  "step": integer,
  "reaction_type": "protection | deprotection | global_deprotection | null"
}

11) Final Validation
Before outputting JSON:
- Ensure phase-specific rules were applied consistently.
- Ensure scheme_steps_count equals the total number of expanded steps.
- Ensure every step is represented exactly once.
- Ensure donor, acceptor, product, and conditions are extracted ONLY for glycosylation steps.
- Ensure non-glycosylation step objects terminate after reaction_type and contain no additional keys.
- Ensure the output contains exactly one of:
  - solution-phase glycosylation objects with "solution_conditions"
  - solid-phase glycosylation objects with "solid_conditions"
- Do NOT output both "solution_conditions" and "solid_conditions" in the same step.
- Do NOT add hidden or inferred steps.
```

## Input

- One reaction scheme image in PNG format
- One reaction description file in TXT format

## Expected Output

A valid pretty-printed JSON object with exactly two top-level keys:

- `reaction_paths`
- `step_analysis`

The `reaction_paths` section should contain terminal-product construction paths.

The `step_analysis` section should contain:

- phase determination: `solution` or `solid`
- expanded scheme step count
- reaction type for every step
- donor / acceptor / product assignment for glycosylation steps only
- phase-specific condition fields for glycosylation steps only
- a short note explaining phase determination

## Rules / Notes

- Use both the scheme image and the reaction description TXT.
- The scheme image is primary for route topology, compound nodes, arrows, branch structure, and terminal product identity.
- The TXT file is secondary and should only support explicit labeled reactants, compound names, SMILES, or missing condition details when linked to the same visual step.
- If image and TXT conflict, rely primarily on the scheme image.
- Do not merge the two internal instruction sets.
- Preserve every drawn reaction arrow as its own step.
- Do not collapse multistep routes into one overall reaction.
- Do not omit explicit numbered on-path intermediates.
- Do not invent hidden intermediates, hidden steps, or chemical identities.
- Use placeholder nodes only for unlabeled intermediates that are visually drawn.
- Identify reaction type for every step.
- Extract donor, acceptor, product, and conditions only for glycosylation steps.
- For non-glycosylation steps, output only `step` and `reaction_type`.
- Apply solution-phase rules only when phase is solution.
- Apply solid-phase rules only when phase is solid.
- Do not output both `solution_conditions` and `solid_conditions` in the same step.
- Preserve compound identifiers exactly, including symbols such as `*`.
- Return valid pretty-printed JSON only.

## Example JSON

```json
{
  "reaction_paths": [
    {
      "path": "11 + 42 -> 43 -> 44 -> 45 -> 15"
    }
  ],
  "step_analysis": {
    "phase": "solution",
    "scheme_steps_count": 3,
    "reaction_steps": [
      {
        "step": 1,
        "reaction_type": "glycosylation",
        "donor": "11",
        "acceptor": "42",
        "product": "43",
        "solution_conditions": {
          "solvent": "explicit solvent if present or null",
          "temperature": "explicit temperature if present or null",
          "time": "explicit time if present or null",
          "promoter_or_activator": "explicit promoter or activator if present or null",
          "other_reagents": "explicit other reagents if present or null",
          "equivalents": "explicit equivalents if present or null",
          "yield": "explicit yield if present or null",
          "stereoselectivity": "explicit stereoselectivity if present or null"
        }
      },
      {
        "step": 2,
        "reaction_type": "deprotection"
      },
      {
        "step": 3,
        "reaction_type": "global_deprotection"
      }
    ],
    "notes": "The scheme is classified as solution-phase because it shows isolated intermediates connected by reaction arrows."
  }
}
```