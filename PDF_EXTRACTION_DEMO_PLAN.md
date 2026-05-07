# PDF Extraction Demo Plan

This demo repo is only for proving the PDF extraction flow.

The goal is not PDF-to-PDF matching yet. The goal is to show, with real engineering PDFs, how we can go from:

```text
PDF file
-> page type detection
-> text/table/OCR extraction
-> normalized extraction data
-> structured engineering data
```

This plan covers only Flow 1 through Flow 4.

## Demo Goal

Build a small, inspectable extraction demo that answers:

- How well can we extract text from AutoCAD/vector engineering PDFs?
- When do we detect scanned/image pages?
- When does OCR fallback run?
- What raw text, tables, and word positions are available?
- What engineering fields can we structure from the PDF?
- What fields are high confidence, low confidence, missing, or OCR-derived?

The demo should produce evidence, not just final values.

Every important extracted field should include:

```text
value
source: text | ocr | mixed | inferred
page number
confidence
raw evidence snippet
warnings if any
```

## Demo Inputs

Use PDFs from `docs/`.

Current sample set:

```text
docs/RC2-100&140 Model A&B Compressor MCS Outline.pdf
docs/Hanbell RC2 100 Exploded Parts Legend.pdf
docs/RC2-100,140,180 Exploded Parts Drawings.pdf
docs/MCP02498.pdf
```

The compressor outline PDF is an important first sample because it is an AutoCAD/vector PDF with selectable text and engineering drawing content.

## Demo Outputs

For each input PDF, write outputs under `outputs/<pdf-name>/`.

Recommended files:

```text
page_detection.json
raw_extraction.json
structured_engineering_data.json
extraction_report.md
```

Purpose:

```text
page_detection.json
  Shows page type classification and OCR decisions.

raw_extraction.json
  Shows normalized page text, raw text, words, tables, OCR boxes, and warnings.

structured_engineering_data.json
  Shows title block, BOM, dimensions, connections, notes, GD&T candidates, process signals, and summary.

extraction_report.md
  Human-readable demo report for review.
```

## Flow 1: PDF Intake And Validation

### Goal

Accept a PDF file and prepare it for extraction.

This flow should not parse engineering data. It only validates and initializes the extraction run.

### Process

```text
PDF path received
-> validate file exists
-> validate file extension is .pdf
-> check file is not empty
-> create output directory
-> create extraction run metadata
-> pass file to Flow 2
```

### Run Metadata

Capture:

```text
input_path
file_name
file_size_bytes
created_at
run_id
output_dir
```

### Failure Cases

Return clean failures for:

```text
file does not exist
file is not a PDF
file is empty
PDF cannot be opened
```

### Flow 1 Output

```json
{
  "input_path": "docs/RC2-100&140 Model A&B Compressor MCS Outline.pdf",
  "file_name": "RC2-100&140 Model A&B Compressor MCS Outline.pdf",
  "file_size_bytes": 221074,
  "run_id": "example-run-id",
  "output_dir": "outputs/RC2-100-140-outline"
}
```

## Flow 2: PDF Page Type Detection With OCR Fallback

### Goal

Decide how each page should be read.

Each page should be classified as:

```text
text_page
image_page
hybrid_page
empty_or_unknown_page
```

Document-level type should be:

```text
text_vector_pdf
scanned_image_pdf
hybrid_pdf
unreadable_pdf
```

### Core Rule

Always try PDF-native text extraction first.

OCR is fallback only when native text extraction is missing or too weak.

```text
Page received
-> try text extraction
-> measure text strength
-> inspect image coverage
-> classify page
-> run OCR only if needed
```

### Text Strength Signals

Measure:

```text
character count
word count
engineering keyword count
dimension/unit pattern count
```

Engineering keywords/patterns:

```text
MODEL
DRAWING
REV
DATE
UNIT
mm
inch
ITEM
QTY
NOTE
Ø
R10
1/2"
DN25
M10
ASME
ISO
GD&T
```

Suggested first-version threshold:

```text
strong_text =
  word_count >= 20
  or character_count >= 100
  or engineering_keyword_count >= 3
```

### Image Strength Signals

Measure:

```text
image_count
largest_image_coverage
total_image_coverage
```

Coverage means visual page area, not image file byte size.

```text
page_area = page_width * page_height
image_area = (x1 - x0) * (y1 - y0)
image_coverage = image_area / page_area
```

Suggested first-version threshold:

```text
large_image =
  largest_image_coverage >= 0.60
  or total_image_coverage >= 0.75
```

Use largest image coverage as the main scanned-page signal. Use total image coverage as a secondary signal for pages made from multiple large image tiles.

### Page Classification Rule

```text
strong_text + not large_image -> text_page
not strong_text + large_image -> image_page
strong_text + large_image -> hybrid_page
not strong_text + not large_image -> empty_or_unknown_page
```

### OCR Behavior

```text
text_page:
  use native text extraction

image_page:
  run OCR
  use OCR text

hybrid_page:
  use native text first
  optionally run OCR when native text looks incomplete

empty_or_unknown_page:
  try OCR if possible
  otherwise mark unreadable
```

OCR should recover visible text only. It does not fully understand CAD geometry.

OCR can extract:

```text
title block text
dimension labels
connection labels
callout numbers
BOM text
drawing notes
revision/date/model text
```

OCR cannot reliably infer:

```text
true 3D geometry
which shape is a compressor body
which circle is a flange
which leader points to which exact component
complete GD&T semantics without visible frame/text context
```

### Flow 2 Output

Write `page_detection.json`.

Example:

```json
{
  "pdf_type": "text_vector_pdf",
  "page_count": 1,
  "pages": [
    {
      "page_number": 1,
      "page_type": "text_page",
      "text_strength": {
        "character_count": 1245,
        "word_count": 210,
        "engineering_keyword_count": 18
      },
      "image_strength": {
        "image_count": 0,
        "largest_image_coverage": 0.0,
        "total_image_coverage": 0.0
      },
      "extraction_method": "text",
      "ocr_used": false,
      "warnings": []
    }
  ],
  "document_warnings": []
}
```

## Flow 3: PDF Text, Layout, OCR, And Table Extraction

### Goal

Create parser-ready extraction data from the Flow 2 detection results.

Flow 2 decides how a page should be read.

Flow 3 prepares the actual raw content package:

```text
normalized text
raw text
word positions
tables
OCR text/boxes/confidence
page dimensions
warnings
```

### Relationship To Flow 2

Flow 2 may already do quick text extraction for detection.

Flow 3 should reuse that work where possible instead of extracting blindly again.

```text
Flow 2:
  quick extraction for detection

Flow 3:
  full extraction package for engineering parsing
```

### Text/Vector Pages

Extract:

```text
plain text
raw text
words with coordinates
tables
page dimensions
```

Word coordinates are important for:

```text
title block location
BOM/table location
notes region
dimension clusters
callout areas
```

### Image Pages

Extract OCR data:

```text
OCR text
OCR lines
OCR word boxes
OCR confidence
```

OCR-derived text should be marked clearly because it is less reliable for:

```text
decimal points
inch marks
degree symbols
small dimensions
rotated text
model numbers
item numbers
GD&T symbols
```

### Hybrid Pages

Combine native PDF extraction and OCR carefully.

```text
Use native text first
Use OCR for image-heavy or missing text regions
Avoid duplicate text where possible
Mark source as text, ocr, or mixed
```

### Table Extraction

Try native table extraction for text/vector pages.

Preserve both:

```text
native extracted tables
raw words with coordinates
```

Reason: engineering tables may not extract cleanly as tables. Flow 4 can reconstruct BOM-like rows from word positions if table extraction fails.

For OCR pages, preserve OCR word boxes and line groupings so later parsing can attempt table-like reconstruction.

### Text Normalization

Normalize lightly.

Recommended:

```text
collapse repeated spaces
remove repeated blank lines
normalize degree/inch/diameter symbols when safe
decode known CID artifacts
preserve original raw text
preserve page boundaries
```

Do not over-normalize engineering values.

### Flow 3 Output

Write `raw_extraction.json`.

Example:

```json
{
  "pdf_type": "text_vector_pdf",
  "page_count": 1,
  "pages": [
    {
      "page_number": 1,
      "page_type": "text_page",
      "extraction_method": "text",
      "text": "...normalized text...",
      "raw_text": "...original extracted text...",
      "page_width": 792,
      "page_height": 1224,
      "words": [
        {
          "text": "MODEL",
          "x0": 100.0,
          "top": 700.0,
          "x1": 150.0,
          "bottom": 715.0,
          "source": "text",
          "confidence": 1.0
        }
      ],
      "tables": [
        {
          "source": "native_table_extraction",
          "rows": [
            ["No.", "Name", "Note"],
            ["1", "Angle valve", "1/4\" Flare"]
          ]
        }
      ],
      "warnings": []
    }
  ],
  "document_warnings": []
}
```

## Flow 4: Structured Engineering Data Parsing

### Goal

Convert parser-ready extraction data into structured engineering data.

Flow 3 gives text, tables, word positions, OCR boxes, and warnings.

Flow 4 produces structured fields like:

```text
title block
drawing type
units
BOM/components
dimensions
connections
notes
drawing structure
GD&T/tolerance candidates
manufacturing/process signals
semantic summary
```

### Parsing Strategy

Use a layered approach:

```text
1. Deterministic parsers for exact values
2. Layout/table heuristics for table/title-block structure
3. LLM assistance for classification, summaries, messy notes, and inferred process signals
4. Validation so LLM output does not override high-confidence exact parser values
```

Project-owned parsers should handle exact fields.

Examples:

```text
title_block_parser:
  "Model RC2-100/140A&B" -> model = RC2-100/140A&B

bom_parser:
  "1 | Angle valve | 1/4\" Flare" -> item_no = 1, component_name = Angle valve, note = 1/4" Flare

dimension_parser:
  "416.5 (16.4)" -> metric_value = 416.5, imperial_value = 16.4

connection_parser:
  "1/4\"NPT, option" -> size = 1/4", type = NPT, option = true
```

The LLM can assist with:

```text
drawing type classification
semantic summary
component category classification
messy note interpretation
manufacturing/process inference
normalizing component names
grouping notes by meaning
```

The LLM should not be the only parser for exact numbers, dates, model names, quantities, or dimensions.

### Required Evidence Model

Every important structured field should include:

```text
value
source: text | ocr | mixed | inferred
page number
confidence
evidence text
warnings
```

Example:

```json
{
  "field": "model",
  "value": "RC2-100/140A&B",
  "source": "text",
  "page": 1,
  "confidence": "high",
  "evidence": "Hanbell Model RC2-100/140A&B",
  "warnings": []
}
```

### 1. Title Block Metadata

Extract:

```text
manufacturer/company
model
drawing name/title
drawing number
revision/version
date
drawn by
checked by
approved by
sheet number
scale
```

Use label patterns and layout position when available.

### 2. Drawing/PDF Type

Classify:

```text
outline drawing
exploded parts drawing
parts legend
RFQ drawing
assembly drawing
detail drawing
spec sheet
datasheet
unknown engineering PDF
```

### 3. Units, Standards, Tolerances, GD&T

Extract:

```text
units: mm | inch | both | unknown
dimension standards
tolerance standards
surface finish standards
inspection standards
explicit +/- tolerances
GD&T candidate symbols/frames
datum references
surface finish values
```

Examples:

```text
UNIT: SI: mm Imperial: (in)
+/- 0.1
ASME Y14.5
ISO 1101
ISO 2768
Ra 1.6
| position symbol | diameter 0.10 | A | B | C |
```

GD&T extraction rule:

```text
Symbol alone -> GD&T symbol candidate or drawing symbol
Feature-control-frame context with tolerance/datum -> actual GD&T requirement candidate
```

For example, a position-like symbol inside a title block/projection symbol or standalone center mark should not be treated as a full GD&T requirement unless tolerance-frame context is present.

### 4. BOM / Components

Extract component rows:

```text
item number
component name
quantity if present
material if present
note/spec
category
page
confidence
evidence
```

### 5. Dimensions

Extract:

```text
linear dimensions
paired metric/imperial dimensions
diameters
radii
angles
tolerances
overall/envelope dimensions when supported by evidence
```

Do not compute true 3D volume or surface area from ordinary PDF drawings.

PDF comparison should use:

```text
stated dimensions
known/inferred envelope dimensions
dimension overlap
dimension tolerances
dimension units
```

Dimension role confidence:

```text
explicit label like Length/Width/Height -> high
layout/dimension cluster -> medium
largest-number fallback -> low
unknown -> keep as dimension candidate
```

### 6. Connections / Ports / Flanges / Valves

Extract:

```text
port names
connection sizes
thread types
flange types
valve details
sensor details
inlet/outlet/discharge/suction/oil drain labels
option flags
```

Examples:

```text
1/4"NPT, option
3/8"Flare, option
1 1/2"
2"
5/8", solder
Discharge flange
Suction flange
Oil drain valve
Discharge temp. sensor
```

### 7. Drawing Notes And Requirements

Extract:

```text
options
special requirements
standards
warnings
assembly notes
inspection notes
surface treatment
material notes
tolerance notes
customer requirements
```

### 8. Drawing Structure

Identify:

```text
outline views
section/detail views
exploded views
parts legend
BOM table
title block
callout balloons
notes block
multiple sheets
projection/title-block symbols
center marks / hole-center symbols
```

For the demo, structure detection can be based on text, tables, layout, and simple visual/layout cues. It does not need full CAD geometry understanding.

### 9. Manufacturing / Assembly Process Signals

Extract explicit process requirements when written:

```text
die casting
casting
machining
welding
forging
stamping
injection molding
heat treatment
anodizing
powder coating
painting
plating
assembly torque
press fit
inspection
```

Explicit process notes are facts.

Inferred process signals are hypotheses and must include evidence and confidence.

Example:

```json
{
  "process": "die casting",
  "evidence_type": "inferred",
  "evidence_text": "aluminum material, draft angle note, casting tolerance",
  "page": 1,
  "confidence": "medium"
}
```

### 10. Semantic Summary

Create a concise meaning-based summary grounded in extracted evidence.

Example:

```text
Hanbell RC2-100/140 compressor outline drawing with dual metric/imperial dimensions, component callouts, BOM-style legend, oil/valve/sensor notes, and MCS title block metadata.
```

The semantic summary is useful later for vector retrieval and LLM comparison, but it should not replace structured fields.

### Flow 4 Output

Write `structured_engineering_data.json`.

Example:

```json
{
  "title_block": {
    "manufacturer": {
      "value": "HANBELL",
      "source": "text",
      "page": 1,
      "confidence": "high",
      "evidence": "HANBELL"
    }
  },
  "drawing_type": {
    "value": "outline drawing",
    "source": "text",
    "page": 1,
    "confidence": "high",
    "evidence": "Dimensional Outline Drawing & Component Description"
  },
  "units": {
    "value": "both",
    "source": "text",
    "page": 1,
    "confidence": "high",
    "evidence": "UNIT SI: mm Imperial: (in)"
  },
  "bom_components": [],
  "dimensions": [],
  "connections": [],
  "notes": [],
  "drawing_structure": {},
  "tolerances_gdnt": [],
  "process_requirements": [],
  "semantic_summary": "",
  "warnings": []
}
```

## Demo Success Criteria

The demo is successful when it can show, for at least the compressor outline PDF:

- document/page classification as text/vector PDF
- extracted raw text and page metadata
- extracted BOM/component table or table-like component rows
- extracted title block fields
- extracted units
- extracted dimensions and paired metric/imperial values
- extracted connections/ports/valves/sensors
- detected drawing structure such as outline drawing, BOM table, title block, callouts
- GD&T candidate handling that does not misclassify center marks/projection symbols as full GD&T requirements
- structured JSON output with evidence, confidence, and source
- markdown report that is readable enough to show stakeholders

## Out Of Scope For This Demo

This demo should not implement:

- PDF-to-PDF matching
- ChromaDB indexing
- fingerprint similarity scoring
- STEP comparison
- production API routes
- full CAD geometry reconstruction from drawings
- certified GD&T interpretation

The demo should only prove extraction capability through structured engineering data.
