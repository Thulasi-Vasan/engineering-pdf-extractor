# RFQ PDF Extraction Flow

This document explains the current RFQ/drawing PDF extraction process from input PDF to final structured output.

## Current Flowchart

```text
Start
  |
  v
User provides PDF path
  |
  v
Flow 1: Intake and validation
  |
  |-- Check file exists
  |-- Check file is a PDF
  |-- Create output folder
  |-- Capture run metadata
  |
  v
Flow 2: Page type detection
  |
  |-- Use pdfplumber to inspect native text
  |-- Count characters, words, engineering keywords, dimensions/units
  |-- Check image count and image coverage
  |
  |-- Classify each page as:
  |     text_page
  |     image_page
  |     hybrid_page
  |     empty_or_unknown_page
  |
  v
Write page_detection.json
  |
  v
Flow 3: Raw extraction
  |
  |-- pdfplumber extracts:
  |     raw/native text
  |     words with coordinates
  |     tables
  |     page size
  |
  |-- PyMuPDF extracts:
  |     vector drawing primitives from page.get_drawings()
  |     primitive bounding boxes
  |     stroke/fill colors
  |     line width
  |     path type
  |
  |-- If page needs OCR:
  |     PyMuPDF renders the page image
  |     AWS Textract extracts OCR text, words, and tables
  |
  v
Flow 3A: Text reconstruction and normalization
  |
  |-- Group words by y-coordinate into visual lines
  |-- Sort words in each line by x-coordinate
  |-- Collapse repeated/overprinted text
  |     Example: TTThhhiiisss -> This
  |-- Recombine spaced capital text
  |     Example: A D V A N C E D -> ADVANCED
  |-- Normalize common CAD/PDF symbol artifacts where safe
  |
  v
Flow 3B: Vector primitive classification
  |
  |-- Classify PyMuPDF vector objects:
  |
  |     normal black line ----------> drawing_line
  |     red line -------------------> leader_line
  |     green/blue line ------------> centerline
  |     small frame/box ------------> gdnt_frame_candidate
  |     long thin line -------------> dimension_line_candidate
  |     larger box -----------------> frame_box / table_box
  |     unclear object -------------> unknown_vector
  |
  v
Write raw_extraction.json
  |
  |-- At this point vectors are still raw evidence:
  |     individual classified primitives only,
  |     not drawing views yet
  |
  v
Flow 4: Region detection
  |
  |-- Text-based regions:
  |     title_block
  |     tolerance_notes
  |     thread_callout_area
  |     engineering_table
  |
  |-- Vector-based regions:
  |     take classified vector primitives from raw extraction
  |     filter useful drawing primitives
  |     group nearby primitives by page coordinates
  |     split dense vector groups into drawing_view candidates
  |
  |-- Example:
  |     PyMuPDF primitive -> drawing_line / leader_line / frame_box
  |     nearby primitives -> page_1_vector_view_1
  |
  |-- Always add fallback:
  |     page_1_drawing_body
  |
  v
Flow 5: Structured engineering parsing
  |
  |-- Parse title block:
  |     model, drawing number, drawing name, dates,
  |     drawn by, approved by, material, company
  |
  |-- Parse units:
  |     inch, mm, or both
  |
  |-- Parse BOM/components:
  |     item number, component name, notes, quantity/material if available
  |
  |-- Parse engineering tables:
  |     thread chart, hole chart, bolt chart, material table,
  |     tolerance table, revision table, unknown engineering table
  |
  |-- Parse dimensions:
  |     linear values, metric/imperial pairs, diameter,
  |     chamfer, angle, ranges
  |     use evidence text coordinates to assign drawing_view
  |     fall back to drawing_body when region is uncertain
  |
  |-- Parse thread requirements:
  |     M3x0.5 - 6g, #10-32 -2A,
  |     minimum full threads, thread chart rows
  |
  |-- Parse tolerance / GD&T candidates:
  |     default tolerances, angle tolerance, chamfer tolerance,
  |     GD&T candidates with review confidence when uncertain
  |
  |-- Parse manufacturing/process requirements:
  |     material, surface finish, heat treatment, finish,
  |     coating/plating, burr/edge break notes
  |
  |-- Parse connections:
  |     NPT, flare, flange, solder, valve/port/sensor labels
  |
  v
Flow 6: Generic engineering requirement projection
  |
  |-- Convert specialized parsed data into one common list:
  |
  |     thread_requirements ----------> engineering_requirements[type=thread]
  |     manufacturing_requirements ---> engineering_requirements[type=material/surface_finish/etc.]
  |     process_requirements ---------> engineering_requirements[type=process]
  |     connections ------------------> engineering_requirements[type=connection]
  |
  |-- Keep specialized sections too
  |-- Use this generic layer for downstream comparison/document filling
  |
  v
Optional Flow 7: Bedrock vision dimension extraction
  |
  |-- PyMuPDF renders page image
  |-- Bedrock vision reads visible dimensions
  |-- Validate vision dimensions:
  |     reject zero/reference values
  |     reject thread-derived false dimensions
  |     merge only when value/unit/type match deterministic dimensions
  |     assign region from matching visible text when available
  |     keep uncertain values in review_dimensions
  |
  v
Write structured_engineering_data.json
  |
  v
Generate extraction_report.md
  |
  |-- Human-readable summary
  |-- Page detection
  |-- Engineering tables and requirements
  |-- Dimensions and review dimensions
  |-- Drawing regions and vector view candidates
  |-- Warnings
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
- How strong is the native text layer?
- How much image coverage exists on the page?

### `raw_extraction.json`

This file stores source evidence from the PDF.

It contains:

- raw page text
- normalized page text
- extracted words
- word coordinates
- reconstructed visual lines
- extracted tables
- OCR output if OCR was used
- PyMuPDF vector drawing primitives

The vector primitives are additive evidence. They are not full CAD geometry.

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

It stores:

- title block fields
- drawing type
- units
- BOM/components
- dimensions
- review dimensions
- connections
- engineering tables
- engineering requirements
- drawing regions
- tolerances/GD&T candidates
- manufacturing/process signals
- semantic summary
- warnings

### `extraction_report.md`

This is the human-readable summary for review/demo.

It is generated from the structured JSON, so if structured JSON has an issue, the report will also reflect that issue.

## PyMuPDF vs pdfplumber

The current pipeline uses both because they solve different parts of the problem.

```text
pdfplumber
  -> native text
  -> words with coordinates
  -> tables

PyMuPDF
  -> page rendering for OCR/vision
  -> vector drawing primitives
  -> colored lines
  -> path bounding boxes
  -> future crop/vision workflows
```

In short:

```text
pdfplumber reads the text/table layer.
PyMuPDF reads the drawing/vector layer.
```

## Current Region Types

The current parser can create these region types:

```text
drawing_body
drawing_view
engineering_table
title_block
tolerance_notes
thread_callout_area
view_label_area
```

Meaning:

- `drawing_body`: whole-page fallback region.
- `drawing_view`: dense vector cluster that likely represents one drawing/view.
- `engineering_table`: detected engineering table area.
- `title_block`: metadata/title block area.
- `tolerance_notes`: standards/tolerance/manufacturing note area.
- `thread_callout_area`: thread-related callout area.
- `view_label_area`: labels like `DETAIL A`, `SECTION A-A`, `VIEW B`.

## Important Limitations

- Vector primitive extraction is not full CAD/STEP geometry parsing.
- `drawing_view` means a likely drawing-view region, not confirmed front/side/top view semantics.
- Dimension-to-view assignment is not fully implemented yet.
- GD&T symbols are still review-confidence unless strongly validated.
- PDF dimensions are drawing-derived values, not true CAD bounding-box values.
- Surface area/volume should not be treated as true part geometry from PDF dimensions alone.

## Current Next Improvements

The next major improvements should be:

1. Improve view segmentation so MCP upper/lower views and RC2 all visual views split more accurately.
2. Assign each dimension to the nearest/overlapping drawing view.
3. Add stronger GD&T validation using text artifacts, vector frame detection, cropped OCR/vision, and symbol dictionaries.
4. Add visual debug output or overlays so detected regions can be reviewed against the PDF.
