# Input Preparation

## Description

This step prepares the raw input files for downstream prompt modules.

The raw paper PDF, Supporting Information file, and figure files are converted into prepared text and image inputs.

The goal is not to extract reaction information at this stage.
The goal is only to prepare clean input materials for later modules.

## Input

- Paper PDF
- Supporting Information PDF / document
- Figure files or extracted figures

## Expected Output

Prepared inputs for downstream modules:

- `main_article_text`
- `supporting_information_text`
- `figure_captions`
- `figure_image_paths`
- `paper_id`
- `figure_id`
- `source_file`
- `page_number`

## Rules / Notes

- This step only prepares text and image inputs.
- Do not extract reaction type, donor, acceptor, product, or reaction conditions in this step.
- The current minimal pipeline assumes these inputs are already prepared.