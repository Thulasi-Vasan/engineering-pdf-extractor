# RFQ PDF Extraction Flow

This document explains the current RFQ/drawing PDF extraction process from input PDF to final structured output.

## Simple Flowchart

```text
Start
  |
  v
User provides PDF path
  |
  v
Flow 1: Intake and Validation
  |
  |-- Check file exists
  |-- Check file is a PDF
  |-- Create output folder
  |-- Capture run metadata
  |
  v
Flow 2: Page Type Detection
  |
  |-- Read each page with native PDF extraction
  |-- Count text, words, engineering keywords, dimensions/units
  |-- Check image coverage
  |
  |-- Classify page as:
  |     text_page
  |     image_page
  |     hybrid_page
  |     empty_or_unknown_page
  |
  v
Write page_detection.json
  |
  v
Flow 3: Raw Extraction
  |
  |-- For text/vector pages:
  |     use native PDF text extraction
  |
  |-- For image-heavy or weak-text pages:
  |     render page image
  |     use AWS Textract OCR fallback
  |
  |-- Extract:
  |     raw text
  |     words with coordinates
  |     tables
  |     page size
  |     OCR results when used
  |
  |-- Reconstruct visual text lines from word coordinates
  |-- Normalize common PDF text artifacts
  |
  v
Write raw_extraction.json
  |
  v
Flow 4: Structured Engineering Parsing
  |
  |-- Read raw extraction evidence
  |-- Parse engineering meaning using deterministic rules
  |
  |-- Extract:
  |     title block fields
  |     units
  |     dimensions
  |     thread requirements
  |     BOM/component tables
  |     engineering tables
  |     connections/ports/valves/sensors
  |     standards
  |     GD&T/tolerance candidates
  |     process/manufacturing notes
  |     drawing type
  |
  |-- Attach evidence, source, confidence, and warnings
  |
  v
Write structured_engineering_data.json
  |
  v
Generate Markdown Report
  |
  |-- Summarize page detection
  |-- Show extraction method per page
  |-- Show parsed engineering data
  |-- Show warnings and review items
  |
  v
Write extraction_report.md
  |
  v
End
```

## Output Files

For each PDF, the agent creates one output folder:

```text
outputs/<pdf-name>/
  page_detection.json
  raw_extraction.json
  structured_engineering_data.json
  extraction_report.md
```

## What Each File Means

### `page_detection.json`

This file explains how each PDF page can be read.

It answers:

- Is the page mostly text/vector?
- Is it mostly an image?
- Is it mixed/hybrid?
- Does it need OCR?

### `raw_extraction.json`

This file stores the extracted evidence from the PDF.

It contains:

- raw page text
- extracted words
- word coordinates
- reconstructed visual lines
- extracted tables
- OCR output if OCR was used

This file should stay close to what the PDF actually contains.

### `structured_engineering_data.json`

This file converts raw PDF evidence into engineering meaning.

Example:

```text
Raw text:
2x 0.010 X 45°

Structured meaning:
chamfer dimension
quantity = 2
size = 0.010 inch
angle = 45 degrees
```

This file is where we store fields like model, drawing number, dimensions, tolerances, standards, and thread requirements.

### `extraction_report.md`

This is the human-readable summary for review/demo.

It is generated from the structured JSON, so if structured JSON has an issue, the report will also reflect that issue.

## Important Notes

- Native PDF text extraction is used first.
- AWS Textract is used as OCR fallback for image-heavy or weak-text pages.
- Bedrock vision dimension extraction is optional and separate from Textract OCR.
- Raw extraction is evidence.
- Structured extraction is interpretation.
- GD&T symbols are treated carefully. If the symbol is uncertain, it should be marked as a review candidate, not a confirmed requirement.
- PDF dimensions are drawing-derived values, not true STEP/CAD geometry. We should not treat them as exact CAD bounding-box dimensions unless the drawing clearly provides that meaning.

