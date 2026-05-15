# Version 3 Updates

This file tracks follow-up work after the LLM final JSON became the main downstream artifact.

## Current Status

Version 2 moved the system toward:

- keeping deterministic extraction as the evidence layer,
- using Claude for semantic enrichment only,
- writing `llm_final_engineering_data.json` as the final downstream JSON,
- preserving deterministic fields while adding labels, descriptions, view labels, warnings, and review items.

The current agent is usable for the main text/vector PDF flow. The next improvements are quality and robustness work for downstream chatbot and form-filling use.

## Compared With Version 2

| V2 Item | V2 Concern | Current Status | V3 Follow-Up |
|---|---|---|---|
| V2-1 | LLM JSON lost nested deterministic fields | Mostly addressed by backend-owned final JSON plus enrichment merge. | Continue validating new sections stay field-complete. |
| V2-2 | Spatial grounding should become bbox/span-aware | Still future work. | Keep as a future parser improvement, not required before chatbot prototype. |

## Version 3 Issues

| Issue | Priority | Area | Note |
|---:|---|---|---|
| V3-1 | medium | Noisy notes cleanup | Some final JSON notes can still be table fragments, duplicate extraction fragments, or low-value text. Keep real engineering notes, but classify/filter noisy fragments. |
| V3-2 | medium | Duplicate warning cleanup | Some fields can show repeated or overlapping warning text. Deduplicate warnings while preserving useful risk signals for the future chatbot. |
| V3-3 | medium | Review item quality | Review items should stay focused on real downstream risks: GD&T uncertainty, duplicate dimensions, unsupported claims, conflicts, unknown target IDs, and OCR/Textract limitations. |
| V3-4 | medium | Frontend duplicate handling | Dimensions now support duplicate-link metadata. Frontend can later collapse or visually link duplicate metric/inch dimensions instead of treating them as independent values. |
| V3-5 | future | OCR/Textract path | OCR works when AWS Textract IAM access is available, but not all testers have that access. Keep OCR-dependent PDFs out of core testing until IAM/access is resolved. |
| V3-6 | future | Parts/exploded drawing support | Exploded-parts callouts need a proper deterministic design and parts-legend/BOM mapping before being merged into the main flow. Abandoned for now. |
| V3-7 | future | Span-aware evidence | Use `pdfplumber.page.search()` or equivalent bbox/span-aware parsing to improve exact evidence grounding and region assignment. |

## Current High Priority

No blocker is high priority for the current agent demo if testing focuses on the supported text/vector PDFs.

The highest-value next product step is a chatbot prototype over `llm_final_engineering_data.json`.

## Demo Window Plan

For the current demo window, avoid large parser rewrites.

Focus order:

1. Use supported demo PDFs such as `MCP02498.pdf` and `RC2-100&140 Model A&B Compressor MCS Outline.pdf`.
2. Apply only small demo-safe cleanup if needed, such as duplicate warning/review noise.
3. Build a chatbot prototype over `llm_final_engineering_data.json`.
4. Consolidate branches into one testing branch near the end.

Do not start the full reconstruction rewrite before the demo.

## Chatbot Direction

The chatbot should use `llm_final_engineering_data.json` as its primary context.

Expected behavior:

- answer from final JSON first,
- cite `evidence`, `page`, `region_id`, confidence, and warnings where available,
- avoid re-reading the PDF for normal questions,
- surface review items when the answer depends on uncertain GD&T, duplicate dimensions, or low-confidence extraction,
- keep raw extraction files as debug artifacts, not as primary chatbot context.

## Deferred Work

These items should not block the chatbot prototype:

- OCR/Textract-only PDFs,
- exploded-parts callout extraction,
- full bbox/span parser rewrite,
- advanced frontend display of every new final JSON field.

## Post-Demo Parser Rewrite Plan

After the chatbot prototype is built and tested, create a dedicated branch for reconstruction cleanup.

Recommended branch:

```text
fix-span-aware-reconstruction
```

Goal:

```text
move parsing away from reconstructed-line-first logic
and toward bbox/span-aware extraction
```

Current weak flow:

```text
reconstruct visual lines
-> regex over reconstructed text
-> infer evidence/region afterward
```

Target flow:

```text
search exact patterns with bbox/span support
-> parse matched value
-> assign evidence and region from match coordinates
```

Candidate implementation:

- use `pdfplumber.page.search(..., return_chars=True)` where available,
- preserve reconstructed lines as debug context,
- make dimensions, threads, tolerances/GD&T candidates, and notes use span-aware evidence incrementally,
- validate one parser class at a time instead of doing a full rewrite in one batch.
