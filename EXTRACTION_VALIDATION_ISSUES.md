# Extraction Validation Issues

This file tracks findings from manually comparing generated extraction output against the source PDF. Use it for parser/OCR/vision issues that should be fixed later.

## Issue Tracker

Status meanings:

- `fixed`: current output has the intended general behavior.
- `partial`: improved, but still has known limitations or needs cleanup.
- `open`: not implemented yet.
- `future`: intentionally deferred hardening work.

| Issue | Status | Area | Current Note |
|---:|---|---|---|
| 1 | partial | GD&T symbol extraction | GD&T candidates are captured, but symbol mapping is still review-confidence only. |
| 2 | partial | CAD/PDF symbol normalization | Diameter artifacts improved; GD&T artifacts still need stronger validation. |
| 3 | fixed | Text normalization | Repeated overprinted text is normalized in reconstructed lines. |
| 4 | fixed | Text reconstruction | Spaced company text is recombined in reconstructed/normalized evidence. |
| 5 | partial | Line reconstruction | Reconstructed lines help, but dense title/tolerance regions can still produce noisy evidence. |
| 6 | partial | Tolerance symbols | Common tolerance artifacts are normalized and parsed; loose duplicate tolerance fragments/evidence noise still need cleanup. |
| 7 | fixed | Title block parsing | MCP title fields now parse; cleanup tracked separately in Issue 14. |
| 8 | fixed | Drawing type | MCP classifies as part manufacturing drawing. |
| 9 | fixed | Standards | `ASME-Y14.5M` is parsed. |
| 10 | fixed | Engineering tables | Thread/item chart is parsed as `engineering_tables`. |
| 11 | partial | Dimensions | Chamfer/diameter/inch dimensions improved; more advanced association still needed. |
| 12 | partial | GD&T/tolerances | Tolerance rows and GD&T candidates are emitted; GD&T remains review-confidence. |
| 13 | partial | Process/manufacturing | Heat treatment/finish no longer over-confirmed; manufacturing cleanup still needs refinement. |
| 14 | open | Title block cleanup | Need page numbers, focused evidence, and generic/specific date precedence. |
| 15 | open | Schema design | Need a generic engineering requirement model so each new PDF type does not require a new top-level section. |
| 16 | open | Engineering tables | Need generic table classification for multiple table types across different PDFs. |
| 17 | open | Thread parsing | Need richer thread fields such as threads-per-inch, chart label linkage, and cleaner evidence. |
| 18 | open | Vision dimension merge | Need safer merging between deterministic dimensions and Bedrock vision dimensions. |
| 19 | open | View segmentation | Need real drawing view/region segmentation for PDFs with multiple diagrams on one page. |
| 20 | future | GD&T validation | Need multi-signal GD&T confirmation using text artifacts, vector frames, cropped vision/OCR, and symbol dictionaries. |
| 21 | open | Surface finish symbols | Need symbol-aware extraction for surface finish values like `63 or better`. |
| 22 | open | Notes classification | Need to split noisy note blocks into standard/legal/manufacturing/tolerance note types. |

## MCP02498.pdf

### Issue 7: Structured title block parser misses MCP02498 fields and extracts false revision

- File checked: `outputs/MCP02498/structured_engineering_data.json`
- Related evidence in raw file: `outputs/MCP02498/raw_extraction.json`
- Structured output currently contains:

```json
"title_block": {
  "revision_version": {
    "value": "ISIONS",
    "source": "text",
    "page": null,
    "confidence": "high"
  }
}
```

- Expected from PDF/raw extraction:

```text
MODEL: LRM200
DWG No.: FM3845
DRAWN BY: E. Pano
CREATED DATE: 8/26/2014
APPROVED BY: R. Walker
APPROVAL DATE: 9/4/2014
ITEM #: SEE CHART
CAGE: 1X8M6
SHEET: 1 OF 1
M3 Male Thread Adapter
MATERIAL: 303 S.S. COLD DRAWN
```

- Actual structured parsing:
  - Incorrectly extracts `ISIONS` from `REVISIONS`.
  - Misses actual model, drawing number, author, dates, item, cage, sheet, part name, and material fields.
- Impact:
  - Title block metadata is mostly unusable for this PDF.
  - Downstream fingerprinting/comparison would miss important identifiers like model and drawing number.
- Likely cause: current title block parser is tuned toward the RC2 drawing layout and field labels, not this MCP title block/table layout.
- Future fix ideas:
  - Add a more general title-block parser that supports label-value pairs like `MODEL:`, `DWG No.:`, `DRAWN BY:`, `CREATED DATE:`, `APPROVED BY:`, `APPROVAL DATE:`.
  - Parse title block fields from extracted tables as well as plain text.
  - Add false-positive guard so `REVISIONS` does not become `revision_version`.
  - Extend schema to include `drawing_number`, `created_date`, `approved_by`, `approval_date`, `item_number`, `cage`, `sheet`, `part_name`, and `material`.

### Issue 8: Drawing type classifier is too generic for MCP02498

- File checked: `outputs/MCP02498/structured_engineering_data.json`
- Structured output currently contains:

```json
"drawing_type": {
  "value": "unknown engineering PDF",
  "source": "text",
  "confidence": "low",
  "evidence": "2x 0.010 X 45°"
}
```

- Expected from PDF/raw extraction: this should be classified more specifically, such as:

```text
part manufacturing drawing
thread adapter detail drawing
```

- Supporting raw evidence:

```text
M3 Male Thread Adapter
THREAD 'T'
MATERIAL: 303 S.S. COLD DRAWN
ALL DIMENSIONS ARE IN INCHES
TOLERANCE
DWG No.: FM3845
```

- Actual structured parsing:
  - Keeps drawing type as `unknown engineering PDF`.
  - Uses weak evidence from a dimension/chamfer callout instead of title/material/thread context.
- Impact:
  - Fingerprinting/comparison may lose useful drawing classification.
  - This PDF may not group correctly with other detail/manufacturing drawings.
- Likely cause: drawing type classifier is currently simple and tuned toward outline/BOM-style drawings.
- Future fix ideas:
  - Add drawing type rules for detail/manufacturing drawings.
  - Use title block/part name/material/thread/tolerance cues for classification.
  - Store both broad type (`engineering drawing`) and specific type (`thread adapter detail drawing`) when possible.

### Issue 9: Structured standards parser misses ASME-Y14.5M

- File checked: `outputs/MCP02498/structured_engineering_data.json`
- Related raw evidence: `outputs/MCP02498/raw_extraction.json`
- Structured output currently contains:

```json
"standards": []
```

- Expected from PDF/raw extraction:

```text
DRAWING INTERPRETATION DIMS. PER ASME-Y14.5M
```

- Expected structured output should include something like:

```json
{
  "value": "ASME-Y14.5M",
  "source": "text",
  "page": 1,
  "confidence": "high",
  "evidence": "DRAWING INTERPRETATION DIMS. PER ASME-Y14.5M"
}
```

- Actual structured parsing: the standards list is empty.
- Impact:
  - Important dimensioning/tolerancing standard metadata is lost.
  - Later comparison may miss standard differences between drawings.
- Likely cause: standards parser is missing or not checking noisy/reconstructed note lines.
- Future fix ideas:
  - Add regex patterns for `ASME`, `Y14.5`, `ASME-Y14.5M`, `ASME Y14.5`, etc.
  - Run standards extraction after line reconstruction/normalization.
  - Preserve exact raw standard text and normalized standard value separately.

### Issue 10: Thread/item chart is present in raw tables but missing from structured output

- File checked: `outputs/MCP02498/structured_engineering_data.json`
- Related raw evidence: `outputs/MCP02498/raw_extraction.json`, table 3.
- Structured output currently contains:

```json
"bom_components": []
```

- Raw extraction contains a useful chart:

```text
ITEM #     CHART#     THREAD SIZE 'T'
MCP02497   -01       1/4-28 -2A
MCP02498   -02       #10-32 -2A
MCP02499   -03       #6-32 -2A
MCP02500   -04       M6x1 -6g
```

- Expected structured representation should include a table type such as `thread_chart`, `variant_chart`, or `item_chart`, for example:

```json
{
  "item_number": "MCP02498",
  "chart_number": "-02",
  "thread_size": "#10-32 -2A"
}
```

- Actual structured parsing:
  - No BOM rows are parsed, which is acceptable if this is not a BOM.
  - But the item/thread chart is not represented anywhere else in structured JSON.
- Impact:
  - Important item-specific engineering requirements are lost.
  - The exact MCP02498 variant/thread size is not available for comparison/fingerprinting.
- Likely cause: current schema/parser expects BOM/component rows and does not support chart-style engineering tables.
- Future fix ideas:
  - Add support for non-BOM engineering tables such as `thread_chart`, `variant_chart`, `item_chart`, or a generic `engineering_tables` section.
  - Detect tables by headers like `ITEM #`, `CHART#`, `THREAD SIZE`.
  - Link current source file/item number (`MCP02498`) to the matching chart row.

### Issue 11: Structured dimension parser misses several MCP02498 dimensions and special forms

- File checked: `outputs/MCP02498/structured_engineering_data.json`
- Related raw evidence: `outputs/MCP02498/raw_extraction.json`
- Structured output currently includes only a small subset:

```text
45°
0.56 inch
0.23 inch
0.0 inch
```

- Raw extraction contains additional visible dimension/tolerance values:

```text
2x 0.010 X 45°
0.56
0.230
0.100
0.075
0.000
n0.281
0.186
0.234
.005 - .015
.X ±0.1"
.XX ±0.01"
.XXX ±0.005"
.XXXX ±0.001"
```

- Expected structured behavior:
  - Parse `2x 0.010 X 45°` as a chamfer/dimension callout with quantity `2x`, size `0.010`, and angle `45°`.
  - Normalize `n0.281` to `Ø0.281` when validated as a diameter callout.
  - Capture linear dimensions like `0.100`, `0.075`, `0.186`, `0.234`.
  - Move default tolerance rows into a structured tolerance section.
  - Capture GD&T/tolerance frames separately instead of losing them.
- Actual structured parsing:
  - Captures only a few values.
  - Misses special forms, diameter symbol artifacts, tolerance frames, and default tolerance table values.
  - Some evidence strings are noisy and merge unrelated nearby values.
- Impact:
  - Dimension matching/fingerprinting would be incomplete for this drawing.
  - Important manufacturing requirements may be missed.
- Likely cause: current deterministic parser handles simple dimension patterns but not CAD-specific symbol artifacts, chamfer notation, tolerance tables, or feature-control frames.
- Future fix ideas:
  - Add dimension pattern parsers for chamfers, diameter/radius, ranges, and inch-only drawings.
  - Run symbol normalization before dimension parsing.
  - Add a dedicated tolerance/GD&T parser separate from normal dimensions.
  - Use word coordinates and line reconstruction so evidence does not combine unrelated dimensions.

### Issue 12: Structured GD&T/tolerance section is empty despite visible candidates

- File checked: `outputs/MCP02498/structured_engineering_data.json`
- Related raw evidence: `outputs/MCP02498/raw_extraction.json`
- Structured output currently contains:

```json
"tolerances_gdnt": []
```

- PDF/raw evidence includes feature-control-frame and tolerance candidates:

```text
c.002
bn.002B
j.002A
ANGLE: ± 1/2°
CHAMFER: ± 5°
.X ±0.1"
.XX ±0.01"
.XXX ±0.005"
.XXXX ±0.001"
```

- Expected structured behavior:
  - Capture GD&T/feature-control-frame candidates with review confidence when symbols are not decoded cleanly.
  - Capture default tolerance table values separately from normal dimensions.
  - Preserve raw symbol text and normalized candidate text.
- Actual structured parsing: no tolerance/GD&T candidates are emitted.
- Impact:
  - Important manufacturing and inspection requirements are missing from structured JSON.
  - PDF-to-PDF comparison may miss tolerance and GD&T differences.
- Likely cause: current parser does not have a dedicated tolerance/GD&T extraction stage and depends on clean native text symbols.
- Future fix ideas:
  - Add a `tolerances_gdnt` parser that handles default tolerance tables and feature-control-frame candidates.
  - Use symbol normalization and vector-frame detection before classifying GD&T.
  - Emit uncertain GD&T rows as `confidence: review` instead of dropping them.

### Future Hardening: Validate GD&T symbols beyond text-artifact mapping

- Current status: GD&T-like text artifacts such as `c.002`, `bn.002B`, and `j.002A` can be mapped to likely symbol candidates, but this is heuristic and should remain `review` confidence.
- Why this matters: custom CAD/PDF font encodings may map letters like `b`, `c`, or `j` differently in other drawings, so text-only mapping is not enough for high-confidence GD&T extraction.
- Stronger future fixes:
  - Inspect actual embedded font/glyph maps when available to decode CAD symbols more reliably.
  - Use vector geometry to detect feature-control-frame boxes and symbol cells.
  - Crop GD&T frame regions and send them to OCR/vision model for symbol confirmation.
  - Combine text artifact, vector frame shape, and vision result before assigning high confidence.
  - Keep the current heuristic as fallback, but only promote to high confidence when at least one independent validation path agrees.

### Issue 13: Process requirement parser overstates heat treatment/finish label

- File checked: `outputs/MCP02498/structured_engineering_data.json`
- Related raw evidence: `outputs/MCP02498/raw_extraction.json`
- Structured output currently contains:

```json
{
  "value": "heat treat",
  "source": "text",
  "page": 1,
  "confidence": "high"
}
```

- PDF/raw evidence shows a label:

```text
HEAT TREATMENT - FINISH:
-
```

- Expected structured behavior:
  - Recognize the `HEAT TREATMENT - FINISH` field.
  - Preserve the actual value after the label, which appears to be `-` / not specified.
  - Avoid treating the label alone as a confirmed heat-treatment requirement.
- Actual structured parsing: emits `heat treat` as a high-confidence process requirement.
- Impact:
  - Manufacturing-process extraction may falsely imply a required heat-treatment process.
  - Later comparison could incorrectly treat this as a process requirement match/difference.
- Likely cause: current parser searches for process keywords and does not distinguish labels from populated requirement values.
- Future fix ideas:
  - Parse process fields as label/value pairs.
  - If value is blank or `-`, emit `not_specified` or a low/medium-confidence field rather than a confirmed process.
  - Keep evidence focused on the process field instead of noisy surrounding legal/title text.

### Issue 1: GD&T/tolerance symbol before `.002` is misread

- File checked: `outputs/MCP02498/raw_extraction.json`
- PDF area: tolerance frame near `0.230` and `0.100`
- Extracted raw text:

```json
{
  "text": "c.002",
  "x0": 90.9595,
  "top": 348.10694124,
  "x1": 121.41361811819999,
  "bottom": 357.1063704,
  "source": "text",
  "confidence": 1.0
}
```

- Expected from PDF: the numeric value `.002` appears with a GD&T/tolerance symbol before it, likely a flatness-style symbol inside/near a feature-control frame.
- Actual extraction: the numeric value is captured, but the symbol is decoded as `c`.
- Impact: raw extraction is only partially correct. Structured GD&T parsing cannot safely classify this as a full tolerance requirement from native text alone.
- Likely cause: the symbol is stored as a special CAD/PDF glyph, custom font character, or vector symbol that native text extraction does not decode correctly.
- Future fix ideas:
  - Preserve glyph/font metadata around suspicious symbol spans.
  - Add symbol normalization for common CAD/GD&T glyph decoding artifacts.
  - Use nearby vector boxes/frames to identify feature-control-frame candidates.
  - Use cropped vision/OCR fallback for symbol-heavy tolerance frames.
  - Mark decoded symbol artifacts like `c.002`, `bn.002B`, `j.002A` as GD&T/tolerance candidates needing review.

### Issue 2: Multiple GD&T/diameter symbols are decoded as letters

- File checked: `outputs/MCP02498/raw_extraction.json`
- PDF area: thread/detail region near `M3x0.5 - 6g`, feature-control frames, and diameter callout.
- Extracted raw text:

```json
[
  {
    "text": "bn.002B",
    "x0": 254.76,
    "top": 435.94694124,
    "x1": 298.506502527,
    "bottom": 446.5063704,
    "source": "text",
    "confidence": 1.0
  },
  {
    "text": "j.002A",
    "x0": 254.76,
    "top": 447.46694124000004,
    "x1": 289.23290579999997,
    "bottom": 457.7863704,
    "source": "text",
    "confidence": 1.0
  },
  {
    "text": "n0.281",
    "x0": 260.04,
    "top": 488.62694124,
    "x1": 286.1759591232,
    "bottom": 497.7463704,
    "source": "text",
    "confidence": 1.0
  }
]
```

- Expected from PDF:
  - `bn.002B` appears visually as a feature-control-frame style tolerance with a GD&T symbol, `.002`, and datum `B`.
  - `j.002A` appears visually as another feature-control-frame style tolerance with a GD&T symbol, `.002`, and datum `A`.
  - `n0.281` appears visually as `Ø0.281` diameter callout.
- Actual extraction:
  - GD&T symbols are decoded as letters like `b`, `j`, and `n`.
  - Diameter symbol `Ø` is decoded as `n`.
- Impact:
  - Raw extraction preserves useful numeric/datum content, but symbol meaning is wrong.
  - Structured parsing may miss GD&T requirements and diameter dimensions unless symbol artifacts are normalized.
- Likely cause: CAD/GD&T symbols are encoded through a custom PDF font/glyph map rather than standard Unicode.
- Future fix ideas:
  - Build an artifact normalization map for this font/PDF style, e.g. `n0.281` -> `Ø0.281` when pattern fits a diameter callout.
  - Detect feature-control frames from vector boxes around `.002` values and datum letters.
  - Capture surrounding vector geometry so symbol meaning can be inferred from the frame, not only text.
  - Send cropped symbol/frame regions to a vision model when native decoding is ambiguous.
  - Add structured fields for `raw_symbol_text`, `normalized_symbol`, `value`, `datum`, and `needs_review`.

### Issue 3: Overprinted note text is extracted with repeated characters

- File checked: `outputs/MCP02498/raw_extraction.json`
- PDF area: proprietary/confidential note block near the title/company area.
- Extracted raw text examples:

```json
[
  {
    "text": "TTThhhiiisss",
    "x0": 383.4,
    "top": 661.5708528,
    "x1": 393.167538647,
    "bottom": 667.4030928,
    "source": "text",
    "confidence": 1.0
  },
  {
    "text": "dddrrraaawwwiiinnnggg",
    "x0": 394.79645621,
    "top": 661.5708528,
    "x1": 413.00691922199996,
    "bottom": 667.4030928,
    "source": "text",
    "confidence": 1.0
  },
  {
    "text": "iiisss",
    "x0": 414.72533775,
    "top": 661.5708528,
    "x1": 418.251675771,
    "bottom": 667.4030928,
    "source": "text",
    "confidence": 1.0
  }
]
```

- Expected from PDF: normal note text, e.g. `This drawing is submitted solely for the information and exclusive use...`.
- Actual extraction: characters are repeated, e.g. `TTThhhiiisss dddrrraaawwwiiinnnggg`.
- Impact:
  - Native text extraction sees the text, but the string is noisy.
  - Notes, process signals, title/company parsing, and semantic summaries may include unreadable repeated-character text.
- Likely cause: the PDF draws the same italic/bold text multiple times with tiny offsets, or uses an overprint/stroked text effect. Visually it looks like one word, but the PDF text layer exposes duplicate glyphs.
- Future fix ideas:
  - Add text normalization that collapses repeated character runs in words when the pattern is consistent, e.g. `TTThhhiiisss` -> `This`.
  - Apply this only to suspicious long words/phrases so valid repeated letters are not damaged.
  - Keep both `raw_text` and `normalized_text` so we do not lose original evidence.
  - Mark normalized text with a warning/source note like `deduplicated_overprinted_text`.

### Issue 4: Widely spaced company name is split into single-letter word entries

- File checked: `outputs/MCP02498/raw_extraction.json`
- PDF area: company/title block text: `ADVANCED SENSOR TECHNOLOGY, INC.`
- Extracted raw word examples:

```json
[
  {"text": "A", "x0": 485.28, "top": 677.4364752, "x1": 487.45583472, "bottom": 682.4666352, "source": "text", "confidence": 1.0},
  {"text": "D", "x0": 488.51948774399995, "top": 677.4364752, "x1": 490.8743216639999, "bottom": 682.4666352, "source": "text", "confidence": 1.0},
  {"text": "V", "x0": 491.99764108799997, "top": 677.4364752, "x1": 494.173475808, "bottom": 682.4666352, "source": "text", "confidence": 1.0}
]
```

- Expected from PDF: `ADVANCED SENSOR TECHNOLOGY, INC.` as one company/title-block phrase.
- Actual extraction: each capital letter is extracted as a separate word/glyph entry.
- Impact:
  - Raw extraction has the characters, but not the phrase.
  - Structured parser may miss or misread company/manufacturer fields.
  - Search for the full company phrase may fail in `words`, though the letters exist by coordinate.
- Likely cause: the PDF uses wide character spacing/tracking, so pdfplumber treats each letter as an independent word.
- Future fix ideas:
  - Add a line reconstruction step using coordinates: group same-line single-letter tokens when gaps are small and font/height are consistent.
  - Preserve both original word tokens and reconstructed line text.
  - Mark reconstructed text with source metadata like `reconstructed_from_glyphs`.
  - Use reconstructed lines for title block/company parsing.

### Issue 5: Adjacent note lines are interleaved during word extraction

- File checked: `outputs/MCP02498/raw_extraction.json`
- PDF area: standard notes/title block region around:
  - `DRAWING INTERPRETATION DIMS. PER ASME-Y14.5M`
  - `SURFACE FINISH 63 OR BETTER`
  - nearby tolerance/model/title block columns
- Extracted raw word examples:

```json
[
  {"text": "D", "top": 705.7144032},
  {"text": "SU", "top": 716.0344032},
  {"text": "R", "top": 705.7144032},
  {"text": "R", "top": 716.0344032},
  {"text": "AW", "top": 705.7144032},
  {"text": "FA", "top": 716.0344032},
  {"text": "IN", "top": 705.7144032},
  {"text": "C", "top": 716.0344032}
]
```

- Expected from PDF:
  - Top line should reconstruct as `DRAWING INTERPRETATION DIMS. PER ASME-Y14.5M`.
  - Next line should reconstruct as `SURFACE FINISH 63 OR BETTER`.
- Actual extraction: words/glyph chunks from the two nearby lines are interleaved by x-position and y-position, producing fragments such as `D SU R R AW FA...`.
- Impact:
  - Raw text order becomes confusing in this region.
  - Standards/tolerance/title-block parsing can miss or corrupt fields.
  - Evidence snippets become noisy because they mix separate visual lines.
- Likely cause: the PDF stores styled/capital text as small chunks, and pdfplumber's reading order merges nearby rows when the vertical spacing is tight.
- Future fix ideas:
  - Reconstruct text lines from `words` using y-coordinate bands before parsing.
  - Sort grouped lines by `top`, then sort words within each line by `x0`.
  - Use a tolerance based on font height to separate close rows.
  - Use reconstructed lines for parser input while preserving original raw word tokens for evidence.

### Issue 6: Tolerance block symbols are decoded incorrectly

- File checked: `outputs/MCP02498/raw_extraction.json`
- PDF area: standard notes/tolerance block containing `ANGLE`, `CHAMFER`, and `TOLERANCE`.
- Extracted raw/table text:

```text
ANGLE:
`1/2~
CHAMFER:
`5~
TOLERANCE:
.X `0.1"
.XX `0.01"
.XXX `0.005"
.XXXX `0.001"
```

- Expected from PDF:

```text
ANGLE: ± 1/2°
CHAMFER: ± 5°
TOLERANCE:
.X ±0.1"
.XX ±0.01"
.XXX ±0.005"
.XXXX ±0.001"
```

- Actual extraction:
  - `±` is decoded as a backtick-like character: `` ` ``.
  - Degree symbol is decoded as `~`.
  - Numeric tolerance values are present.
- Impact:
  - The raw extraction contains the tolerance data, but structured parsing cannot safely interpret it without symbol normalization.
  - Engineering comparison may miss tolerance differences if these values remain as noisy text.
- Likely cause: CAD/PDF font glyph encoding for tolerance symbols does not map cleanly to Unicode.
- Future fix ideas:
  - Normalize common artifacts in tolerance contexts: `` ` `` -> `±`, `~` -> `°`.
  - Apply normalization contextually near labels like `ANGLE`, `CHAMFER`, `TOLERANCE`, and known tolerance patterns.
  - Preserve original raw evidence plus normalized value fields.
  - Add structured tolerance rows for `.X`, `.XX`, `.XXX`, `.XXXX`, angle, and chamfer defaults.
  - Suppress loose duplicate fragments like `±1`, `±5`, `±0.005` when they are already represented by structured default tolerance rows.
  - Prefer focused evidence such as `ANGLE: ±1/2°` over wide noisy title-block/tolerance context.

### Issue 14: Structured title block fields need generic page/evidence/date cleanup

- File checked: `outputs/MCP02498/structured_engineering_data.json`
- This is a **general parser issue**, not an MCP02498-specific issue.
- Observed structured title block output is mostly correct, but has cleanup problems:
  - Several fields have `"page": null` even though the evidence is from page 1.
  - Generic `date` duplicates `created_date` when the drawing has a specific `CREATED DATE` label.
  - Evidence snippets are too wide and include unrelated nearby title block/tolerance text.

Observed examples:

```json
{
  "date": {
    "value": "8/26/2014",
    "page": null,
    "evidence": "REMOVE BURRS ... DRAWN BY: E. Pano CREATED DATE: 8/26/2014 | TOLERANCE:"
  },
  "created_date": {
    "value": "8/26/2014",
    "page": null,
    "evidence": "REMOVE BURRS ... DRAWN BY: E. Pano CREATED DATE: 8/26/2014 | TOLERANCE:"
  }
}
```

- Expected generic behavior:
  - If a value is extracted from a page, set that page number on the field.
  - Do not create a generic `date` field from `CREATED DATE`, `APPROVAL DATE`, or other more specific labels unless the PDF has a real generic `Date` label.
  - Keep evidence short and label-focused when possible, such as `MODEL: LRM200` or `DWG No.: FM3845`.
- Impact:
  - Validation is harder because evidence contains unrelated content.
  - Downstream fingerprinting may treat duplicated date fields as separate metadata.
  - Page-level traceability is weaker when `page` is null.
- Future fix ideas:
  - Make title-block parser return value plus page plus focused evidence from the exact matched line/table cell.
  - Add label precedence: specific labels like `CREATED DATE` and `APPROVAL DATE` should not populate generic `date`.
  - Use reconstructed line/table evidence first, then fall back to wider context only if exact evidence is unavailable.

### Issue 15: Need generic engineering requirement schema for non-thread PDF requirements

- File checked: `outputs/MCP02498/structured_engineering_data.json`
- This is a **general schema design issue**, not an MCP02498-specific issue.
- Current improvement added `thread_requirements`, which is useful for MCP02498 because that drawing has thread callouts and a thread chart.
- But future engineering drawings may contain many other requirement types, such as:
  - welding requirements
  - casting/die casting requirements
  - machining requirements
  - coating/plating/finish requirements
  - heat treatment requirements
  - hardness requirements
  - torque requirements
  - adhesive/sealant requirements
  - press-fit requirements
  - inspection requirements
  - hole/drill charts
  - finish charts
  - revision/change tables
- Risk:
  - If we add a new top-level section for every PDF-specific requirement type, the schema will become hard to maintain.
  - New PDFs will keep forcing schema changes instead of fitting a general extraction model.
- Expected generic direction:

```json
{
  "engineering_requirements": [
    {
      "requirement_type": "thread",
      "value": "M3x0.5 - 6g",
      "parsed_fields": {
        "thread_size": "M3",
        "pitch": 0.5,
        "thread_class": "6g",
        "minimum_full_threads": 3
      },
      "page": 1,
      "region_id": "page_1_thread_callout_area",
      "confidence": "high",
      "evidence": "M3x0.5 - 6g (MINIMUM 3 FULL THREADS)"
    }
  ]
}
```

- Future fix ideas:
  - Add a generic `engineering_requirements` list with `requirement_type`, `value`, `parsed_fields`, `page`, `region_id`, `source`, `confidence`, `evidence`, and `warnings`.
  - Keep specialized sections like `thread_requirements` only as convenience views if needed.
  - Feed known requirement parsers into the generic model first, then optionally project into specialized lists.
  - Use generic requirement types such as `thread`, `finish`, `material`, `heat_treatment`, `coating`, `welding`, `casting`, `machining`, `assembly`, `inspection`, `torque`, `connection`, and `hole_chart`.

### Issue 16: Need generic engineering table classification for different PDF table types

- File checked: `outputs/MCP02498/structured_engineering_data.json`
- This is a **general table parsing issue**, not an MCP02498-specific issue.
- Current output correctly stores the MCP table as:

```json
{
  "table_type": "thread_or_item_chart",
  "headers": ["item_number", "chart_number", "thread_size"]
}
```

- The MCP table is accurate, but future PDFs may contain many other table types, such as:
  - BOM/component table
  - thread chart
  - hole/drill chart
  - bolt chart
  - finish/coating chart
  - material/spec table
  - tolerance table
  - inspection table
  - torque table
  - revision table
  - variant/configuration chart
- Risk:
  - Current table classification is too narrow.
  - Unknown useful tables may be ignored or classified too generically.
  - Multiple tables on the same page need stable `table_index`, `page`, and evidence so downstream parsers can use them safely.
- Expected generic behavior:
  - Store every useful table in `engineering_tables`.
  - Classify table type using headers and table keywords.
  - If uncertain, keep the table as `unknown_engineering_table` with `confidence: review`, instead of dropping it.
  - Preserve page, table index, headers, rows, evidence, confidence, and warnings.
- Future fix ideas:
  - Add table type classifiers for `thread_chart`, `hole_chart`, `bolt_chart`, `revision_table`, `finish_table`, `material_table`, `tolerance_table`, `inspection_table`, and `torque_table`.
  - Add `table_index` or stable table ID to `EngineeringTable`.
  - Feed important rows into generic `engineering_requirements` after table classification.

### Issue 17: Thread requirements need richer generic parsing fields and table linkage

- File checked: `outputs/MCP02498/structured_engineering_data.json`
- This is a **general thread parsing issue**, not an MCP02498-specific issue.
- Current output captures thread requirements, including:

```text
M3x0.5 - 6g (MINIMUM 3 FULL THREADS)
MCP02498 | -02 | #10-32 -2A
```

- Remaining limitations:
  - Unified thread callouts like `#10-32 -2A` and `1/4-28 -2A` do not expose the `32` or `28` threads-per-inch value as a structured field.
  - `THREAD 'T'` is captured as a review label, but it is not linked to the chart column `THREAD SIZE 'T'`.
  - Local callout evidence can include neighboring dimension text like `0.000`.
- Expected generic behavior:

```json
{
  "thread_size": "#10",
  "threads_per_inch": 32,
  "thread_class": "2A",
  "source_table": "thread_chart",
  "chart_reference": "T",
  "evidence": "#10-32 -2A"
}
```

- Future fix ideas:
  - Extend `ThreadRequirement` with `threads_per_inch`, `chart_reference`, and `source_table`.
  - Parse unified thread forms as `major_size + threads_per_inch + class`.
  - Link labels like `THREAD 'T'` to matching table headers like `THREAD SIZE 'T'`.
  - Trim evidence to the actual callout span where possible.

### Issue 18: Vision dimension merge can mix unrelated evidence into exact text dimensions

- File checked: `outputs/MCP02498/structured_engineering_data.json`
- This is a **general vision/parser merge issue**, not an MCP02498-specific issue.
- Observed behavior:
  - Deterministic parser extracts exact text dimensions like `2x 0.010 X 45°` and `Ø0.281`.
  - Bedrock vision also returns nearby visual dimension candidates.
  - Current merge logic can attach unrelated vision evidence to an already exact dimension.
- Example:

```text
2x 0.010 X 45° | Vision: Line extending from 0.230 to 0.330 | ...
```

- Risk:
  - Exact text dimensions become harder to validate.
  - Vision may incorrectly merge local dimensions, thread values, or unrelated nearby values.
  - Values like `M3` may be misinterpreted by vision as `3.0 mm thread_pitch`.
- Expected generic behavior:
  - Keep high-confidence exact text dimensions clean.
  - Merge vision only when value, unit, dimension type, and nearby evidence clearly match.
  - If vision finds a possible related value but the match is uncertain, keep it as a separate `review` candidate.
  - Do not let vision overwrite deterministic exact values.
- Future fix ideas:
  - Add stricter merge rules by value, unit, type, evidence text, and region.
  - Add warning when vision-only dimension is not grounded in raw text.
  - Treat thread notation like `M3x0.5` with parser-first rules so vision does not misclassify `M3` as pitch.

### Issue 19: Multiple drawing views/diagrams on one page need real view segmentation

- Current output has basic `drawing_regions`, such as:
  - `page_1_drawing_body`
  - `page_1_title_block`
  - `page_1_thread_callout_area`
  - `page_1_tolerance_notes`
  - `page_1_engineering_tables`
- This is only a first step. It does **not** yet split separate drawing views such as:
  - front view
  - side view
  - top view
  - section view
  - detail view
  - exploded/detail diagrams
- Risk:
  - If a page has multiple diagrams, dimensions from one view can be associated with the wrong feature/view.
  - Text/leader lines/GD&T from dense drawings can mix across regions.
- Current first-pass region limitations observed in `outputs/MCP02498/structured_engineering_data.json`:
  - `thread_callout_area` is too broad and overlaps much of the page/title block.
  - `engineering_table_area` does not yet include table coordinates.
  - Region overlap priority is not defined, so title block/table/notes/drawing body assignments can conflict.
- Expected generic behavior:
  - Detect separate view/diagram regions on each page.
  - Assign dimensions, callouts, GD&T, notes, and leader-line text to a region before structured parsing.
  - Keep title blocks, tables, and notes separate from drawing body regions.
- Future fix ideas:
  - Add `Flow 3.5: Drawing Region / View Segmentation`.
  - Use coordinate clustering, PyMuPDF vector paths, view labels like `DETAIL A` / `SECTION A-A`, and optional Bedrock vision review.
  - Add `region_id` and `region_type` to parsed dimensions, requirements, GD&T candidates, and notes.
  - Add table bounding boxes when available.
  - Add region priority rules such as `title_block > engineering_table > tolerance_notes > callout_area > drawing_body`.

### Issue 20: GD&T symbols need multi-signal validation beyond native text extraction

- Current behavior:
  - pdfplumber/native text can extract GD&T symbol areas as artifacts like `c.002`, `bn.002B`, and `j.002A`.
  - The parser maps these to review-confidence GD&T candidates.
- This is not enough for high confidence because CAD/PDF font encodings can vary across drawings.
- Expected robust approach:
  - Use pdfplumber native text for raw text and word coordinates.
  - Use PyMuPDF vector paths to detect feature-control-frame boxes and compartments.
  - Crop the feature-control-frame region.
  - Use Textract/Bedrock vision on the crop to confirm the visual symbol.
  - Compare with a GD&T symbol dictionary.
  - Upgrade confidence only when multiple signals agree.
- Proposed confidence behavior:
  - clean native symbol + valid frame context = `high`
  - artifact text + valid frame + cropped vision agreement = `medium` or `high`
  - artifact text only = `review`
  - symbol alone without frame/tolerance/datum context = `review`
- Useful future implementation pieces:
  - `gdnt_frame_detector.py` using PyMuPDF `page.get_drawings()`
  - cropped image generation around candidate frames
  - `gdnt_symbol_dictionary`
  - confidence scoring based on signal agreement

### Issue 21: Surface finish symbol/value extraction misses embedded visual value

- File checked: `outputs/MCP02498/structured_engineering_data.json`
- PDF area checked: standard notes surface finish line.
- Observed PDF text visually contains:

```text
SURFACE FINISH 63 OR BETTER
```

- Current structured output contains:

```text
finish requirement: SURFACE FINISH OR BETTER
```

- Actual issue:
  - The parser captures the surface finish phrase.
  - The value `63` is missed or not preserved.
  - The `63` appears attached to a surface finish symbol/visual mark, so plain text extraction may not reliably capture it.
- Expected generic behavior:

```json
{
  "requirement_type": "surface_finish",
  "value": "63 or better",
  "source": "text_or_symbol",
  "confidence": "medium",
  "evidence": "SURFACE FINISH 63 OR BETTER"
}
```

- Risk:
  - Surface roughness/finish requirements are manufacturing-critical.
  - Other PDFs may use surface finish symbols with values that are not cleanly represented in native text.
- Future fix ideas:
  - Add surface finish symbol/value detection.
  - Use reconstructed text first, then crop the surface finish note region for OCR/vision if the value is missing.
  - Add parser patterns for `SURFACE FINISH <value> OR BETTER`.
  - Store this under generic `engineering_requirements` or `manufacturing_requirements` with requirement type `surface_finish`.

### Issue 22: Notes output mixes legal, standard, manufacturing, and tolerance text

- File checked: `outputs/MCP02498/structured_engineering_data.json`
- Current `notes` output includes broad/noisy note blocks such as:

```text
HEAT TREATMENT - FINISH: STANDARD NOTES: (Unless Otherwise Specified) ...
```

and a large multi-line block containing:

```text
HEAT TREATMENT - FINISH
STANDARD NOTES
ANGLE
ALL DIMENSIONS ARE IN INCHES
ASME-Y14.5M
SURFACE FINISH
REMOVE BURRS
TOLERANCE
```

- Actual issue:
  - Different note types are mixed together.
  - Legal/disclaimer text, standard notes, tolerance rows, and manufacturing notes should not all appear as one generic note.
- Expected generic behavior:
  - Split notes into typed categories, such as:
    - `standard_notes`
    - `legal_notes`
    - `manufacturing_notes`
    - `tolerance_notes`
    - `inspection_notes`
    - `general_notes`
  - Preserve original evidence, but avoid duplicating notes that are already parsed into specific sections like `tolerances_gdnt` or `manufacturing_requirements`.
- Future fix ideas:
  - Add note classification by keywords and region.
  - Deduplicate notes already represented as structured requirements.
  - Keep long note blocks only when they cannot be split safely.
