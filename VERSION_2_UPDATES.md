# Version 2 Updates

This file tracks the next direction for the extraction flow.

## Direction

`llm_final_engineering_data.json` is the final downstream JSON for later form filling and report generation.

The deterministic artifacts are still required and should remain available:

- `page_detection.json`
- `raw_extraction.json`
- `structured_engineering_data.json`
- `extraction_report.md`

The LLM finalizer depends on deterministic extraction evidence:

```text
page_detection summary
+ selected raw_extraction evidence
+ structured_engineering_data
+ rendered 300 DPI page image
-> llm_final_engineering_data.json
```

## Current Version 2 Issues

| Issue | Status | Area | Note |
|---:|---|---|---|
| V2-1 | future | LLM final JSON completeness | Some nested deterministic fields are compressed or missing in `llm_final_engineering_data.json`. The final JSON should preserve deterministic fields and add LLM semantic fields instead of replacing them. |
| V2-2 | future | Spatial grounding | Parser is still partially page-text-first. Later, move toward bbox/span-aware grounding using `pdfplumber.page.search()` or equivalent spatial parsing. |

## V2-1 Details: LLM Final JSON Completeness

The LLM JSON is now cleaner for downstream use, but some nested structured fields are not preserved.

Examples:

- `dimensions` should preserve fields such as `dimension_type`, `quantity`, `angle_value`, `angle_unit`, `role`, `role_confidence`, `normalized_callout`, `source`, `secondary_value`, and `imperial_value`.
- `threads` should preserve fields such as `chart_reference`, `minimum_full_threads`, `quantity`, `relief_note`, `source`, and `source_table`.
- `tables` should preserve `source` and `table_index`.
- `drawing_regions` should preserve coordinates: `x0`, `top`, `x1`, `bottom`, and `source`.

Target behavior:

```text
deterministic fields + LLM semantic fields
```

The LLM should enrich records with fields such as `label`, `description`, `view_label`, and `semantic_label`, but it should not drop deterministic evidence fields.

## V2-2 Details: Spatial Grounding

Current parser logic still often works like:

```text
find value in page text
-> recover bbox/region later
```

Future parser logic should move toward:

```text
find value with bbox/span evidence
-> assign region from coordinates immediately
```

`pdfplumber.page.search()` is a likely next step because it can return matched text, bbox coordinates, and character objects for parsed values.
