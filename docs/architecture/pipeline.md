# PDF CAD Drawing Extraction Pipeline

**Project**: Structured extraction of parts, dimensions, and annotations from CAD engineering drawings delivered as PDF files.  
**Output format**: JSON — designed for downstream system ingestion.

---

## Table of Contents

1. [Problem Statement](#1-problem-statement)
2. [What We Learn from the Sample Drawing](#2-what-we-learn-from-the-sample-drawing)
3. [Architecture Overview](#3-architecture-overview)
4. [Stage-by-Stage Pipeline](#4-stage-by-stage-pipeline)
   - [Stage 0 — PDF Ingestion & Classification](#stage-0--pdf-ingestion--classification)
   - [Stage 1 — Text & Vector Extraction](#stage-1--text--vector-extraction)
   - [Stage 2 — Structural Parsing](#stage-2--structural-parsing)
   - [Stage 3 — Spatial Association](#stage-3--spatial-association)
   - [Stage 4 — LLM Enrichment & Validation](#stage-4--llm-enrichment--validation)
   - [Stage 5 — Output & Confidence Scoring](#stage-5--output--confidence-scoring)
5. [Output Schema](#5-output-schema)
6. [Risks, Edge Cases, and Mitigations](#6-risks-edge-cases-and-mitigations)
7. [Technology Stack](#7-technology-stack)
8. [What Is Deferred](#8-what-is-deferred)

---

## 1. Problem Statement

Customers provide PDF files containing multi-view CAD engineering drawings (currently AutoCAD-generated). Each drawing includes:

- **Multiple orthographic views** of a mechanical assembly (front, end, cross-section, detail).
- **Bubble annotations** — circled integers labeling each part at its location on the drawing.
- **A Bill of Materials (BOM) table** — maps each bubble number to a part name and specification note (e.g., connection type, optional/standard status).
- **Dimensional annotations** — linear dimensions in dual units (SI in mm, Imperial in inches, shown in parentheses).
- **AutoCAD glyphs** that qualify dimensions, such as:
  - `Ø` — diameter
  - `R` — radius
  - `4×` — quantity prefix (e.g., `4-Ø18` = four holes, 18 mm diameter)
  - Positional tolerance framing (`□`, `⊥`, `∥`, etc.) when present
- **A title block** — structured metadata: model number, drawing name, revision, date, drawn-by, units, company.

The goal is to extract all of this into a well-structured, validated JSON document per drawing.

---

## 2. What We Learn from the Sample Drawing

> **File**: `RC2-100&140 Model A&B Compressor MCS Outline.pdf`  
> **Creator**: AutoCAD 2015 — English 2015  
> **Page count**: 1  
> **Page size**: 792 × 1224 pt (A3 portrait, displayed landscape at 270° rotation)

This analysis directly informs the pipeline design:

| Finding | Implication |
|---|---|
| **Font is ArialMT** (standard TrueType) | Native text layer is fully extractable by PyMuPDF — no OCR needed for this class of file |
| **No embedded raster images** | The drawing is 100% vector geometry — circles, lines, leader arrows, and text are all PDF path objects |
| **Page rotation = 270°** | PyMuPDF returns text coordinates in the pre-rotation mediabox space. All spatial logic must account for this transform |
| **29,187 vector paths** | Bubble circles, leader lines, dimension lines, and the drawing itself are all vector paths — detectable and usable for spatial association |
| **201 extractable text spans** | All text — part numbers, names, notes, dimensions, title block — is in the text layer |
| **BOM table present on the same page** | The BOM is ground truth; it must be extracted first and used to validate everything else |
| **Dual units on every dimension** | SI value and imperial value always appear as a pair. Pairing logic is required |
| **Bubble numbers appear twice** | Once in the BOM table (small, ~8.6pt) and once as in-drawing callouts (larger, ~16.2pt). These are two representations of the same datum |
| **Ø glyph in dimension text** | e.g., `4-Ø18` — present in native text layer, needs symbol normalization |

**What the sample confirms the pipeline must handle:**
- Page rotation normalization before any spatial reasoning
- BOM-first extraction as the anchor for part records
- Bubble-to-part spatial mapping via vector circle detection
- Dimension pairing (SI + imperial) and symbol normalization
- Title block segmentation by font size and region

---

## 3. Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────────┐
│                             PDF Input                                   │
└─────────────────────────────┬───────────────────────────────────────────┘
                              │
                    ┌─────────▼─────────┐
                    │  Stage 0          │
                    │  Ingestion &      │
                    │  Classification   │
                    └─────────┬─────────┘
                              │  determines: vector / raster / hybrid
                    ┌─────────▼─────────┐
                    │  Stage 1          │
                    │  Extraction       │◄── PyMuPDF (text + vectors)
                    │  (text / paths)   │◄── OCR fallback if needed
                    └─────────┬─────────┘
                              │  raw spans with bounding boxes + paths
                    ┌─────────▼─────────┐
                    │  Stage 2          │
                    │  Structural       │  Title block, BOM table,
                    │  Parsing          │  dimension spans, bubble spans
                    └─────────┬─────────┘
                              │  typed, structured objects
                    ┌─────────▼─────────┐
                    │  Stage 3          │
                    │  Spatial          │  Associate bubbles→parts,
                    │  Association      │  pair SI/Imperial dimensions,
                    │                   │  attach dims to views
                    └─────────┬─────────┘
                              │  linked part/dimension graph
                    ┌─────────▼─────────┐
                    │  Stage 4          │
                    │  LLM Enrichment   │◄── Vision LLM (multimodal)
                    │  & Validation     │    for ambiguous cases only
                    └─────────┬─────────┘
                              │  validated, enriched records
                    ┌─────────▼─────────┐
                    │  Stage 5          │
                    │  Output &         │  Pydantic schema validation
                    │  Confidence       │  Confidence scores, flags
                    └─────────┬─────────┘
                              │
                    ┌─────────▼─────────┐
                    │   JSON Output     │
                    └───────────────────┘
```

The LLM is a **last-resort enrichment step**, not the primary extraction engine. This keeps cost low and results deterministic for well-formed drawings.

---

## 4. Stage-by-Stage Pipeline

### Stage 0 — PDF Ingestion & Classification

**Purpose**: Determine what type of content is on each page so the correct extraction path is chosen.

**Steps**:
1. Open the PDF with PyMuPDF.
2. Read page metadata: rotation, mediabox, creator string.
3. Count text spans from `page.get_text("dict")`.
4. Count embedded images from `page.get_images()`.
5. Count vector paths from `page.get_drawings()`.

**Classification logic**:

| Condition | Classification | Action |
|---|---|---|
| Many text spans, many paths, no images | **Vector drawing** (ideal) | Proceed to Stage 1A |
| Few/no text spans, one large image | **Rasterized drawing** | Rasterize at 300 DPI, run OCR |
| Few text spans, many paths | **SHX font drawing** | Rasterize + OCR (text is in paths) |
| Mix of images + text | **Hybrid** | Both paths in parallel |

> **SHX font detection**: AutoCAD's built-in fonts (Simplex, Romans, etc.) are compiled to line segments — they appear as vector paths, not text glyphs. The tell-tale sign is a high path count combined with near-zero text spans on a clearly labeled drawing.

**Output**: A `PageProfile` object with `{rotation, width, height, text_span_count, image_count, path_count, classification}`.

---

### Stage 1 — Text & Vector Extraction

**Purpose**: Extract all raw textual and geometric content with spatial coordinates.

#### 1A — Native Text (Vector path)

Use `page.get_text("dict")` to extract all text spans. Each span yields:
- `text` — the string content
- `bbox` — bounding box `[x0, y0, x1, y1]` in original mediabox coordinates
- `font` — font name
- `size` — font size in points

**Coordinate normalization**: If `page.rotation != 0`, the bounding boxes are in the original (pre-rotation) coordinate system. All coordinates must be transformed into a canonical display-space system before downstream use. For 270° rotation on a 792×1224 pt page:

```
display_x =  y0_original
display_y =  792 - x1_original
```

#### 1B — Vector Paths (for bubble detection)

Use `page.get_drawings()` to extract path objects. Bubble circles will appear as closed elliptical paths. A path is a bubble candidate if:
- Its bounding box is approximately square (aspect ratio near 1.0)
- Its bounding box diagonal is within the expected bubble size range (typically 10–20 pt in drawing space)
- It has no fill or a white fill with a black stroke

#### 1C — OCR Fallback (rasterized drawings only)

Render the page at 300 DPI using `page.get_pixmap(matrix=fitz.Matrix(300/72, 300/72))`, then pass the PNG to an OCR engine. Recommended: **AWS Textract** or **Google Document AI** (better than Tesseract on engineering drawings — they handle tables and multi-column layouts natively).

---

### Stage 2 — Structural Parsing

**Purpose**: Classify each extracted text span into one of five semantic categories.

#### 2.1 — Title Block Extraction

The title block occupies the bottom strip of the drawing. Characteristics:
- Relatively large font sizes (10–22 pt vs. 8–9 pt for drawing annotations)
- Low x0 coordinate range (in the original rotated space, this is the bottom of the page)
- Contains known fields: Model, Name, Date, Drawn By, Ver., units label

Extracted fields:
```
model_number, drawing_name, revision, date, drawn_by, units_primary, units_secondary, company
```

#### 2.2 — BOM Table Extraction

The BOM table is the **anchor** for all part records. It must be extracted before attempting spatial association.

**Detection**: The BOM is identified by the presence of "No.", "Name", "Note" column headers close together in coordinate space.

**Column structure** (from the sample drawing):
- A two-panel layout: parts 1–14 on the left panel, parts 15–N on the right panel
- Within each panel: `No.` | `Name` | `Note` columns separated by y0 thresholds

**Grouping algorithm**:
- Text spans in the BOM region are grouped by their x0 coordinate (each unique x0 = one BOM row)
- Within a row, spans are assigned to No./Name/Note based on y0 band thresholds derived from header positions
- Rows with the same x0 but different y0 panel bands = different parts (left panel vs. right panel)

**Output** (example):
```json
{"no": 1, "name": "Angle valve", "note": "1/4\"Flare"},
{"no": 7, "name": "Check valve", "note": "1 1/2\""},
{"no": 25, "name": "Solenoid valve", "note": "Stepless(NC or NO), Option"}
```

#### 2.3 — Bubble Number Extraction

In-drawing bubble labels are identified by:
- Content matching `\d{1,2}` (one or two digits)
- Font size ≤ 9 pt (small callout size in drawing space)
- Spatial proximity to a circular vector path (the bubble ring)

The same numbers also appear larger (16.2 pt) as the in-drawing callout labels on the view. Both are captured; the BOM table version is treated as canonical.

#### 2.4 — Dimension Extraction

Dimension spans are identified by:
- Content matching SI pattern: bare numbers (`903`, `241.5`, `4-Ø18`)
- Content matching Imperial pattern: number in parentheses (`(55.6)`, `(9.5)`)
- Font size between 8–11 pt
- Located in the drawing body (not the BOM or title block region)

**Symbol normalization table**:

| Raw text | Normalized meaning |
|---|---|
| `Ø` or `Ã˜` (encoding artifact) | Diameter |
| `4-Ø18` | 4× holes, diameter 18 |
| `R12` | Radius 12 |
| `(x.x)` | Imperial equivalent (inches) |
| `±0.1` | Symmetric tolerance |
| `+0.05 / -0.02` | Asymmetric tolerance (two spans) |

**SI/Imperial pairing**: Each SI dimension value has a corresponding imperial value in parentheses spatially adjacent to it. Pairing is done by finding the closest parenthesized span within a proximity threshold on the same dimension line axis.

#### 2.5 — View Label Extraction

Labels such as `SECTION A-A`, `DETAIL B`, `FRONT VIEW` are identified by:
- All-caps text
- Larger font size relative to dimension annotations
- Spatial isolation from the BOM and title block

---

### Stage 3 — Spatial Association

**Purpose**: Link bubble numbers on the drawing to their BOM entries and to their approximate physical location on the assembly.

#### 3.1 — Bubble-to-BOM Mapping

This is straightforward: the bubble number IS the BOM row key. Every `bubble_number` in the drawing maps directly to the BOM entry with the matching `no`.

#### 3.2 — Bubble Location on Drawing

Each bubble has an (x, y) centroid in drawing space, and belongs to a view region. The view region is determined by:
1. Extracting view label bounding boxes (from Stage 2.5).
2. Assigning each bubble to the view whose region contains the bubble centroid.

#### 3.3 — Dimension-to-Feature Association

Dimensions are attached to geometric features (edges, holes, flanges) via dimension lines. Fully automated association of dimensions to specific features is complex and is handled in two tiers:

- **Tier 1 (deterministic)**: Dimensions with explicit labels like `4-Ø18` are self-describing — quantity and diameter are encoded in the text.
- **Tier 2 (LLM-assisted)**: Overall envelope dimensions (`903 mm`, `548.5 mm`) and positional dimensions are flagged with a `spatial_context` field populated by the vision LLM in Stage 4.

---

### Stage 4 — LLM Enrichment & Validation

**Purpose**: Resolve ambiguities that rule-based extraction cannot handle reliably. The LLM is only invoked for flagged items.

#### When the LLM is invoked

| Trigger | Example |
|---|---|
| Dimension with no clear spatial context | `60 mm` with no nearby feature label |
| Bubble whose circle was not detected in vector paths | Possible SHX or encoding artifact |
| BOM entry with ambiguous or truncated name | Multi-span text that wasn't grouped correctly |
| Unexpected symbols not in normalization table | New GD&T or AutoCAD glyph variant |
| Cross-view dimension reference | Dimension spans two view regions |

#### Prompt structure

The LLM receives **two inputs simultaneously**:

1. **High-resolution PNG** of the page (or cropped region, 300 DPI)
2. **Structured JSON context** of what has already been extracted:

```json
{
  "page": 1,
  "rotation_deg": 270,
  "title_block": { "model": "RC2-100/140A&B", "units_si": "mm", "units_imperial": "in" },
  "bom": [ {"no": 1, "name": "Angle valve", "note": "1/4\" Flare"}, "..." ],
  "extracted_spans": [
    {"text": "60", "bbox_display": [x, y, x1, y1], "size": 9.4, "probable_type": "dimension_si"},
    {"text": "(2.4)", "bbox_display": [...], "probable_type": "dimension_imperial"},
    "..."
  ],
  "flagged_items": [
    {"reason": "no_spatial_context", "span_text": "60", "span_bbox": [...]}
  ]
}
```

The LLM is asked to return only the resolution of the flagged items, not to re-extract everything. This minimises token usage and hallucination surface area.

**Recommended models**: GPT-4o or Gemini 1.5 Pro. Both handle technical drawings and GD&T symbols reliably.

---

### Stage 5 — Output & Confidence Scoring

**Purpose**: Assemble all extracted data into the final JSON document and attach confidence metadata.

#### Confidence scoring

Each extracted item is tagged with a confidence level:

| Level | Meaning |
|---|---|
| `high` | Extracted deterministically from native text layer with clear structural signal |
| `medium` | Extracted deterministically but relied on proximity heuristics (e.g., dimension pairing) |
| `low` | LLM-inferred or extracted from rasterized/OCR'd content |
| `review` | Conflicting signals or missing data — flagged for human review |

Items tagged `review` are collected into a `review_queue` array in the output for human-in-the-loop handling.

#### Pydantic schema validation

All output is passed through a Pydantic model before serialisation. Required fields that are missing or of wrong type will elevate confidence to `review` automatically.

---

## 5. Output Schema

```json
{
  "source_file": "RC2-100&140 Model A&B Compressor MCS Outline.pdf",
  "extraction_timestamp": "2026-05-05T18:00:00Z",
  "title_block": {
    "model_number": "RC2-100/140A&B",
    "drawing_name": "Compressor outline",
    "revision": "06",
    "date": "05/28/2024",
    "drawn_by": "ILM",
    "company": "Micro Control Systems, Inc.",
    "units_si": "mm",
    "units_imperial": "in"
  },
  "parts": [
    {
      "no": 1,
      "name": "Angle valve",
      "note": "1/4\" Flare",
      "locations": [
        {"view": "front", "centroid_mm": [x, y], "confidence": "high"}
      ]
    },
    {
      "no": 7,
      "name": "Check valve",
      "note": "1 1/2\"",
      "locations": [
        {"view": "front", "centroid_mm": [x, y], "confidence": "high"},
        {"view": "end", "centroid_mm": [x, y], "confidence": "medium"}
      ]
    }
  ],
  "dimensions": [
    {
      "si_value": 903.0,
      "si_unit": "mm",
      "imperial_value": 55.6,
      "imperial_unit": "in",
      "qualifier": null,
      "quantity": null,
      "view": "front",
      "confidence": "high"
    },
    {
      "si_value": 18.0,
      "si_unit": "mm",
      "qualifier": "diameter",
      "quantity": 4,
      "description": "bolt circle holes",
      "view": "end",
      "confidence": "high"
    }
  ],
  "views": ["front", "end", "side"],
  "review_queue": [],
  "extraction_stats": {
    "total_parts": 27,
    "parts_high_confidence": 27,
    "total_dimensions": 28,
    "dimensions_high_confidence": 24,
    "llm_calls_made": 0
  }
}
```

---

## 6. Risks, Edge Cases, and Mitigations

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| **SHX fonts** — text compiled to line segments, invisible to text layer | Medium (AutoCAD default fonts) | High | Detect at Stage 0 via low span count; fall back to rasterise + OCR |
| **Text-as-paths** — all text converted to vector outlines | Low–Medium | High | Same detection; rasterise at 300 DPI and run OCR |
| **Page rotation not normalised** | Certain on landscape drawings | Medium | Always apply rotation transform before any spatial logic |
| **Stacked tolerances** — `+0.05` and `-0.02` as separate spans | Medium | Low | Pair by proximity on same dimension line; flag if unpaired |
| **Two-column BOM** spills into three or more panels | Low | Medium | Detect panel count dynamically from "No." header positions |
| **Duplicate bubble numbers** (same part in multiple views) | High | Low | Allow `locations` to be a list; group by part number |
| **Multi-page drawings** | Certain at scale | Medium | Run the full pipeline per page; then merge parts by number across pages |
| **Imperial-only or SI-only drawings** | Low (per unit label) | Low | Read unit annotation from title block; adjust pairing logic accordingly |
| **BOM absent** (dimensions only, no parts table) | Low for this customer | High | Detect at Stage 2; flag entire document for LLM-only extraction |
| **LLM hallucination** on small or dense text | Medium | High | Pre-classify spans before sending; validate LLM output against extracted BOM; never accept a part name the LLM invented that doesn't appear in the BOM |
| **GD&T symbols in private Unicode range** | Medium | Medium | Maintain a normalisation table; fall back to image crop + LLM if symbol is unknown |
| **Drawing scale not encoded** | Medium | Low (schema already uses nominal values) | Record scale from title block; note if absent |

---

## 7. Technology Stack

| Layer | Tool | Rationale |
|---|---|---|
| **PDF parsing** | `pymupdf` (PyMuPDF) | Fast, exposes text layer, vector paths, images, and annotations. Handles rotation. |
| **Rasterisation** | `pymupdf` `page.get_pixmap()` | Built-in; no separate renderer needed |
| **OCR fallback** | AWS Textract or Google Document AI | Superior table extraction over Tesseract on engineering drawings |
| **Data validation** | `pydantic` v2 | Schema enforcement and confidence-based field promotion |
| **Vision LLM** | GPT-4o or Gemini 1.5 Pro | Spatial reasoning, GD&T symbol interpretation, ambiguity resolution |
| **Package management** | `uv` | Fast, reproducible Python environments |
| **Output serialisation** | `json` (stdlib) or `orjson` | Downstream-agnostic |

---

## 8. What Is Deferred

The following are out of scope for the initial implementation and will be revisited as the customer's drawings evolve:

- **Leader line tracing**: Following a leader arrow from a bubble back to the exact surface or hole it points to requires geometric intersection of vector paths — computationally intensive and not required for the current output schema.
- **GD&T tolerance frames**: Feature control frames (boxes with flatness, perpendicularity, etc. symbols) are a separate sub-grammar. The normalisation table handles common cases; full GD&T parsing is deferred.
- **Drawing revision diff**: Comparing two revisions of the same drawing to detect changed dimensions or added parts.
- **3D model linkage**: Associating extracted parts to a corresponding STEP or IGES file.
- **Automated test harness**: A golden-set comparison against manually verified extractions for regression testing.
