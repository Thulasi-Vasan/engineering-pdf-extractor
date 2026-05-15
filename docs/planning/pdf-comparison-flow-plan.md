# PDF-to-PDF Comparison Flow Plan

Scope for the current work:

- Compare PDF query files against PDF corpus files only.
- Keep STEP-to-STEP comparison separate and unchanged.
- Do not support PDF-to-STEP or STEP-to-PDF matching in this phase.
- Build the plan flow by flow before implementation.

## Flow 1: PDF Upload And Mode Selection

### Goal

Receive a PDF upload and route it into the PDF-to-PDF pipeline.

This flow does not parse engineering content yet. It only decides:

- Is the uploaded file a PDF?
- Is this a corpus upload or a query comparison upload?
- Should this file enter the PDF comparison pipeline?

### Process

```text
User uploads file
-> API checks that the file is a PDF
-> reject non-PDF files from PDF endpoints
-> save corpus PDF for indexing, or temporarily save query PDF for comparison
-> pass the PDF to Flow 2: PDF Type Detection
```

### API Endpoints

PDF-specific endpoints:

```text
POST   /api/v1/repo/pdf-files
GET    /api/v1/repo/pdf-files
DELETE /api/v1/repo/pdf-files/{file_id}
POST   /api/v1/compare/pdf
```

Existing STEP endpoints remain separate:

```text
POST /api/v1/repo/step-files
GET  /api/v1/repo/step-files
DELETE /api/v1/repo/step-files/{file_id}
POST /api/v1/compare/step
```

### Matching Boundary

PDF mode must compare only PDFs:

```text
PDF query -> PDF corpus only
```

No cross-format matching in this phase:

```text
PDF -> STEP  not supported
STEP -> PDF  not supported
```

### Registry Data

Each corpus PDF record should store:

```text
file_id
file_name
stored_path
chunks_path
fingerprint_path
size_bytes
status
file_type = "pdf"
record_scope
created_at
indexed_at
```

The `file_type = "pdf"` field is required so the shared storage/indexing layer can separate PDF files from STEP/CAD files.

### User-Facing Errors

This flow should return clean errors for upload-level problems:

```text
Only PDF files are supported for this endpoint.
Uploaded file is empty.
No PDF corpus files have been indexed yet.
```

Scanned/image-only PDF handling belongs to Flow 2.

### Decision

Keep this flow strict and simple:

- PDF endpoints accept PDFs only.
- STEP endpoints accept STEP files only.
- Store `file_type` clearly.
- Do not parse engineering data in this flow.
- Do not mix PDF and STEP corpus records during retrieval or comparison.

## Flow 2: PDF Type Detection With OCR Fallback

### Goal

Detect how each PDF page can be read before engineering parsing starts.

This flow decides whether a page is:

- a text/vector page with selectable PDF text
- a scanned/image page that needs OCR
- a hybrid page with both selectable text and image content
- an empty or unreadable page

### Core Rule

Always try normal PDF text extraction first.

OCR is a fallback, not the primary extraction method:

```text
Page received
-> try text/layout extraction
-> measure extracted text strength
-> inspect image coverage
-> classify page
-> use extracted text or OCR fallback based on classification
```

Text/vector PDFs usually produce cleaner engineering data than OCR, especially for dimensions, symbols, title blocks, and BOM tables.

### Page Detection Signals

Use two main signals per page.

Signal 1: text strength

```text
character count
word count
engineering keyword count
dimension/unit pattern count
```

Engineering keywords and patterns include examples like:

```text
MODEL
DRAWING
REV
DATE
UNIT
mm
inch
BOM
ITEM
QTY
416.5
1/2"
DN25
M10
```

Signal 2: image strength

```text
number of images on page
largest image area
image coverage compared with page area
```

A scanned drawing page often has one large image covering most of the page.

### Suggested First-Version Thresholds

Start with simple thresholds and tune them using real PDFs in `docs/`.

```text
strong_text =
  word_count >= 20
  or character_count >= 100
  or engineering_keyword_count >= 3

large_image =
  image_coverage >= 0.60
```

Do not rely on word count alone. Engineering drawings may have few words but still contain useful values like model numbers, dimensions, units, and connection labels.

### Page Classification

```text
strong_text + not large_image -> text_page
not strong_text + large_image -> image_page
strong_text + large_image -> hybrid_page
not strong_text + not large_image -> empty_or_unknown_page
```

Examples:

```text
AutoCAD/vector drawing:
extractable title block, dimensions, and callouts
-> text_page

Scanned drawing:
little/no extractable text, one large page image
-> image_page

Selectable title block over scanned drawing:
extractable title block plus large image
-> hybrid_page

Blank/broken page:
no useful text and no clear image
-> empty_or_unknown_page
```

### OCR Fallback Behavior

Run OCR at page level when normal text extraction is weak.

```text
text_page:
  use normal extracted text

image_page:
  run OCR
  use OCR text

hybrid_page:
  use normal extracted text first
  optionally run OCR if the extracted text looks incomplete

empty_or_unknown_page:
  try OCR if possible
  otherwise mark the page unreadable
```

A PDF can be mixed, so page-level fallback is better than whole-document fallback.

### OCR Limitation

OCR recovers visible text from the drawing image. It does not fully understand CAD geometry.

OCR can help extract:

```text
title block fields
dimension labels
connection labels
callouts
BOM text
drawing notes
revision/date/model text
```

OCR cannot reliably infer:

```text
this shape is a compressor body
this circle is a flange
this arrow points to this component
this section view corresponds to this outline view
true 3D geometry
```

So scanned/image PDFs should be supported, but with lower extraction confidence when OCR is used.

### Output To Next Flow

Flow 2 should produce page-level extraction metadata for Flow 3.

Example structure:

```json
{
  "pdf_type": "hybrid_pdf",
  "page_count": 3,
  "pages": [
    {
      "page_number": 1,
      "page_type": "text_page",
      "extraction_method": "text",
      "text": "...",
      "ocr_confidence": null,
      "warnings": []
    },
    {
      "page_number": 2,
      "page_type": "image_page",
      "extraction_method": "ocr",
      "text": "...",
      "ocr_confidence": 0.82,
      "warnings": ["OCR used; dimensions and symbols may need validation"]
    }
  ],
  "document_warnings": []
}
```

### User-Facing Failure Cases

If no usable text can be extracted even after OCR:

```text
We could not extract readable engineering text from this PDF.
```

If OCR is required but not available in the environment:

```text
This PDF appears to be scanned/image-only, but OCR is not available.
```

### Decision

Use text/layout extraction first for every page. Use OCR only when extracted text is missing or too weak. Store extraction method, page type, confidence, and warnings so later parsing and matching can treat OCR-derived data more carefully.

## Flow 3: PDF Text And Table Extraction

### Goal

Convert the page detection result from Flow 2 into normalized, parser-ready raw extraction data.

Flow 2 already does quick text extraction to decide whether each page is text-based, image-based, hybrid, or unreadable. Flow 3 should reuse that work where possible and complete the extraction package needed by later engineering parsing.

Flow 3 does not yet decide engineering meaning such as:

```text
model = RC2-100
unit = mm
BOM has 27 components
connection size = 1/2" NPT
```

That belongs to Flow 4. Flow 3 only prepares readable page content.

### Relationship To Flow 2

Flow 2:

```text
Quick extraction
-> measure text strength
-> inspect image coverage
-> classify page
-> decide text extraction vs OCR fallback
```

Flow 3:

```text
Reuse Flow 2 extracted text where possible
-> extract or finalize full page text
-> extract word positions
-> extract tables when available
-> include OCR text/boxes/confidence when used
-> normalize text lightly
-> preserve page/source/warning metadata
```

So Flow 3 should not blindly duplicate all extraction work. It should turn detection-level extraction into parser-ready extraction.

### What "Usable Text" Means

Usable text means text that is ready for engineering parsing, not just text that exists.

It should include:

```text
normalized page text
page number
source method: text | ocr | mixed
confidence when available
word positions when available
tables when available
warnings when extraction quality is uncertain
```

Example raw PDF text:

```text
MODEL     RC2-100
UNlT      mm
(cid:20)(cid:19)°C
```

Example usable text:

```text
MODEL RC2-100
UNIT mm
110°C
```

With metadata:

```json
{
  "page_number": 1,
  "source": "text",
  "confidence": 1.0
}
```

### Text/Vector Page Extraction

For text/vector pages, use PDF-native extraction first.

Extract:

```text
plain text
words with coordinates
tables
page dimensions
```

Useful tools:

```python
page.extract_text()
page.extract_words()
page.extract_tables()
```

Word coordinates matter because engineering drawings often use layout:

```text
title block near bottom/right
BOM table near side/bottom
dimensions around drawing views
notes grouped together
```

### Image Page Extraction

For scanned/image pages, use OCR output from Flow 2 or run OCR if Flow 2 only marked the page as requiring OCR.

Extract:

```text
OCR text
OCR lines
OCR word boxes if available
OCR confidence if available
```

OCR text should keep source and confidence metadata because scanned drawings are more error-prone.

Common OCR risk areas:

```text
decimal points
inch marks
degree symbols
small dimension values
rotated text
model numbers
item numbers
```

### Hybrid Page Extraction

For hybrid pages, combine PDF-native extraction and OCR carefully.

```text
Use PDF-native text first
Use OCR for image-heavy areas or when native text looks incomplete
Avoid duplicating the same text twice
Mark source as text, ocr, or mixed
```

Hybrid output should preserve both sources when useful because native text may capture the title block while OCR may capture labels embedded in the scanned drawing image.

### Table Extraction

For text/vector PDFs, try native table extraction:

```python
page.extract_tables()
```

This may detect BOM or parts-list tables.

However, table extraction may be incomplete or messy, so Flow 3 must also preserve raw text and word positions. Later flows can reconstruct BOM-like rows from text if table extraction fails.

For OCR pages, table extraction is harder. Flow 3 should preserve OCR word boxes and lines so Flow 4 can attempt table-like row detection later.

### Text Normalization

Normalize lightly and carefully.

Recommended normalization:

```text
collapse repeated spaces
remove obvious repeated blank lines
decode known CID artifacts
normalize common degree/inch symbols
preserve page boundaries
preserve original raw text when possible
```

Example CID mappings:

```text
(cid:20) -> 1
(cid:19) -> 0
(cid:131) -> °
```

Do not over-normalize engineering values because small changes can change meaning.

### Output To Flow 4

Flow 3 should produce a normalized extraction object.

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
      "text": "...",
      "raw_text": "...",
      "words": [
        {
          "text": "MODEL",
          "x0": 100,
          "top": 700,
          "x1": 150,
          "bottom": 715,
          "source": "text",
          "confidence": 1.0
        }
      ],
      "tables": [
        {
          "source": "pdfplumber",
          "rows": [
            ["ITEM", "PART NAME", "QTY"],
            ["1", "BODY", "1"]
          ]
        }
      ],
      "warnings": []
    }
  ],
  "document_warnings": []
}
```

### Decision

Flow 3 should reuse Flow 2 extraction where possible, then create a complete raw extraction package for Flow 4. Keep plain text, raw text, word positions, tables, source method, confidence, and warnings. Native PDF text is preferred over OCR, but OCR is included when required.

## Flow 4: Engineering Data Parsing

### Goal

Convert normalized raw PDF extraction data from Flow 3 into structured engineering data.

Flow 3 answers:

```text
What readable text, tables, word positions, OCR boxes, and page metadata do we have?
```

Flow 4 answers:

```text
What engineering information does that content represent?
```

Example:

```text
Raw text:
MODEL RC2-100 UNIT mm REV A DATE 2024

Structured data:
model = RC2-100
unit = mm
revision = A
date = 2024
```

### Important Rule

Engineering PDFs are not consistent. Not every PDF will contain every field.

The parser should:

- extract what is present
- leave missing fields empty
- keep evidence text and page number
- store confidence/source for important fields
- avoid inventing hard facts

### What "Parser" Means Here

Parsers are project-owned code, not external libraries by default.

A parser is a focused piece of logic that turns raw PDF text/tables into structured fields.

Examples:

```text
title_block_parser:
  "MODEL: RC2-100" -> model = RC2-100

bom_parser:
  "1 | COVER | 1 | ALUMINUM" -> item_no = 1, component_name = COVER, quantity = 1

dimension_parser:
  "416.5 (16.4)" -> metric_value = 416.5, imperial_value = 16.4

connection_parser:
  "1/2\" NPT OIL DRAIN" -> size = 1/2", type = NPT, label = OIL DRAIN
```

Libraries like `pdfplumber` and OCR help extract raw content. These parsers provide the engineering meaning.

### Parsing Strategy

Use a layered approach:

```text
1. Deterministic parsers/rules for exact fields
2. Layout/table heuristics for title blocks, BOM tables, notes, and dimension clusters
3. LLM assistance for classification, summaries, messy note interpretation, and inferred signals
4. Validation/normalization so LLM output does not override high-confidence exact values
```

Rules and regex should handle exact values:

```text
model numbers
dates
revisions
units
dimensions
quantities
connection sizes
explicit process words
```

The LLM should act as an assistant for:

```text
drawing type classification
semantic summary
component category classification
messy note interpretation
manufacturing/process inference
normalizing component names
grouping notes by meaning
```

The LLM should not be the only parser for exact values because it may guess, alter numbers, or invent missing information.

### Main Data Categories

Flow 4 should parse these categories:

```text
1. Title block metadata
2. Drawing/PDF type
3. Units and standards
4. BOM/components
5. Dimensions
6. Connections/ports/flanges/valves
7. Drawing notes and requirements
8. Drawing structure
9. Manufacturing/assembly process signals
10. Semantic summary
```

### 1. Title Block Metadata

Extract fields such as:

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

Title blocks are often near the bottom or right side of a drawing, so layout position can improve confidence.

### 2. Drawing/PDF Type

Classify the engineering PDF type:

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

This helps later comparison because an outline drawing should not be scored the same way as an exploded parts legend.

### 3. Units And Standards

Extract:

```text
units: mm | inch | both | unknown
dimension standard
tolerance standard
surface finish standard
material standard
inspection standard
```

Examples:

```text
UNIT: mm
DIMENSIONS ARE IN INCHES
ISO 2768
ASME Y14.5
Ra 1.6
```

### 4. BOM / Components

Parse component rows from native tables or table-like text.

Fields:

```text
item number
component name
quantity
material
spec/notes
category
source page
confidence
evidence text
```

Example:

```json
{
  "item_no": "12",
  "component_name": "Discharge valve",
  "quantity": 1,
  "category": "valve",
  "notes": "1/2 inch NPT",
  "page": 1,
  "confidence": "high",
  "evidence": "12 | Discharge valve | 1 | 1/2 inch NPT"
}
```

### 5. Dimensions

Extract dimension-like values:

```text
linear dimensions
paired metric/imperial dimensions
diameters
radii
angles
tolerances
envelope/overall dimensions when supported by evidence
```

Examples:

```text
416.5 (16.4)
300
Ø25
R10
90°
+/- 0.1
```

Do not assume every large number is an envelope dimension. Prefer context:

```text
L x W x H
Length
Width
Height
Overall
Outline
Envelope
```

Dimension role confidence:

```text
explicit label -> high confidence
layout/dimension cluster -> medium confidence
largest-number fallback -> low confidence
unknown role -> keep as dimension candidate
```

For PDFs, do not claim true 3D volume or surface area unless the drawing explicitly provides those values. Unlike STEP files, PDFs usually do not contain enough reliable 3D geometry to compute actual volume or surface area.

Instead, compare:

```text
stated dimensions
key dimension overlap
known envelope dimensions
dimension units and tolerances
```

### 6. Connections / Ports / Flanges / Valves

Extract connection requirements and related labels:

```text
port names
connection sizes
thread types
flange types
valve details
sensor details
inlet/outlet/discharge/suction/oil drain labels
```

Examples:

```text
1/2" NPT
DN25
M10
SAE flange
oil drain
discharge port
temperature sensor
pressure valve
```

This is a high-value signal for RFQ/drawing comparison.

### 7. Drawing Notes And Requirements

Extract notes such as:

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

Notes may carry important differences that do not appear in the BOM or dimensions.

### 8. Drawing Structure

Identify whether the PDF contains:

```text
outline views
section/detail views
exploded views
parts legend
BOM table
title block
callouts
notes block
multiple sheets
```

For the first version, this can be based on text/table/layout clues instead of full visual geometry understanding.

### 9. Manufacturing / Assembly Process Signals

Extract process requirements directly when written in the PDF, and infer only when enough evidence exists.

Explicit process notes should have high confidence:

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

Example explicit extraction:

```json
{
  "process": "die casting",
  "evidence_type": "explicit",
  "evidence_text": "DIE CAST ALUMINUM",
  "page": 1,
  "confidence": "high"
}
```

Inferred process signals should be marked as inferred and lower confidence.

Example inference:

```json
{
  "process": "die casting",
  "evidence_type": "inferred",
  "evidence_text": "aluminum material, draft angle note, casting tolerance",
  "page": 1,
  "confidence": "medium"
}
```

Decision rule:

```text
Explicit process notes are treated as facts.
Inferred process signals are treated as hypotheses with evidence and confidence.
```

### 10. Semantic Summary

Create a concise summary of what the engineering PDF describes.

Example:

```text
Hanbell RC2 compressor outline drawing with metric/imperial dimensions, title block metadata, port/valve/sensor notes, and component callouts.
```

The summary can be generated with LLM assistance, but should be grounded in extracted evidence.

### Output To Flow 5

Flow 4 should output one structured engineering data object.

Example:

```json
{
  "title_block": {},
  "drawing_type": {},
  "units": {},
  "standards": [],
  "bom_components": [],
  "dimensions": [],
  "connections": [],
  "notes": [],
  "drawing_structure": {},
  "process_requirements": [],
  "semantic_summary": "",
  "warnings": []
}
```

### Decision

Flow 4 should be evidence-based. Deterministic parsers should extract exact values first. LLM assistance can classify, summarize, normalize messy notes, and infer process signals, but it should not override high-confidence exact parser values. For PDFs, compare stated drawing dimensions and requirements rather than pretending we have STEP-like 3D volume or surface area.

## Flow 5: PDF Chunk Creation

Status: To be discussed.

## Flow 6: Universal Fingerprint Schema

Status: To be discussed.

## Flow 7: PDF Corpus Indexing

Status: To be discussed.

## Flow 8: PDF Query Comparison

Status: To be discussed.

## Flow 9: Drawing Comparison Summary

Status: To be discussed.

## Flow 10: LLM Comparison And Ranking

Status: To be discussed.

## Flow 11: API Response And Error Handling

Status: To be discussed.
