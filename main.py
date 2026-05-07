from __future__ import annotations

import argparse
import sys
from pathlib import Path

from rfq_drawing_extractor import extract_pdf


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Extract structured engineering data from an RFQ/drawing PDF."
    )
    parser.add_argument("pdf_path", type=Path, help="Path to the PDF to extract.")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="Optional output directory. Defaults to outputs/<safe-pdf-name>/.",
    )
    parser.add_argument(
        "--vision-dimensions",
        action="store_true",
        help="Use a vision LLM to add visually detected dimension candidates.",
    )
    parser.add_argument(
        "--vision-model",
        default=None,
        help="Optional vision model override. For Bedrock, defaults to BEDROCK_VISION_MODEL.",
    )
    args = parser.parse_args()

    try:
        result = extract_pdf(
            args.pdf_path,
            output_dir=args.output_dir,
            use_vision_dimensions=args.vision_dimensions,
            vision_model=args.vision_model,
        )
    except (FileNotFoundError, ValueError, RuntimeError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    print("Extraction complete")
    print(f"Page detection: {result.page_detection_path}")
    print(f"Raw extraction: {result.raw_extraction_path}")
    print(f"Structured data: {result.structured_data_path}")
    print(f"Report: {result.report_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
