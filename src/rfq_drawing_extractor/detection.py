from __future__ import annotations

import re
from pathlib import Path

from .models import ImageStrength, PageDetection, PageDetectionResult, TextStrength
from .normalization import normalize_text, text_preview


ENGINEERING_KEYWORDS = (
    "MODEL",
    "DRAWING",
    "REV",
    "DATE",
    "UNIT",
    "ITEM",
    "QTY",
    "NOTE",
    "NAME",
    "MM",
    "INCH",
    "NPT",
    "FLARE",
    "FLANGE",
    "VALVE",
    "SENSOR",
    "ASME",
    "ISO",
    "GD&T",
)

DIMENSION_UNIT_RE = re.compile(
    r"(?i)(?:\b\d+(?:\.\d+)?\s*(?:mm|in|inch|°)|\b\d+\s*/\s*\d+\s*\"|Ø\s*\d+|R\s*\d+|\+/-|±)"
)


def detect_pdf_pages(pdf_path: Path) -> PageDetectionResult:
    try:
        import pdfplumber
    except ImportError as exc:
        raise RuntimeError("pdfplumber is required. Install dependencies with uv sync.") from exc

    pages: list[PageDetection] = []
    document_warnings: list[str] = []

    with pdfplumber.open(str(pdf_path)) as pdf:
        for index, page in enumerate(pdf.pages, start=1):
            raw_text = page.extract_text() or ""
            normalized_text = normalize_text(raw_text)
            text_strength = measure_text_strength(normalized_text)
            image_strength = measure_image_strength(page)
            page_type = classify_page(text_strength=text_strength, image_strength=image_strength)
            extraction_method = method_for_page(page_type)
            warnings = []
            if page_type == "empty_or_unknown_page":
                warnings.append("No strong native text or large image signal detected.")

            pages.append(
                PageDetection(
                    page_number=index,
                    page_type=page_type,
                    extraction_method=extraction_method,
                    text_strength=text_strength,
                    image_strength=image_strength,
                    ocr_used=extraction_method in {"ocr", "mixed"},
                    native_text_preview=text_preview(normalized_text),
                    native_text=normalized_text,
                    warnings=warnings,
                )
            )

    pdf_type = classify_document(pages)
    if pdf_type == "unreadable_pdf":
        document_warnings.append("No readable pages were detected.")

    return PageDetectionResult(
        pdf_type=pdf_type,
        page_count=len(pages),
        pages=pages,
        document_warnings=document_warnings,
    )


def measure_text_strength(text: str) -> TextStrength:
    words = re.findall(r"\b[\w/&.-]+\b", text)
    upper_text = text.upper()
    keyword_count = sum(1 for keyword in ENGINEERING_KEYWORDS if keyword in upper_text)
    dimension_count = len(DIMENSION_UNIT_RE.findall(text))
    character_count = len(text)
    word_count = len(words)
    strong_text = word_count >= 20 or character_count >= 100 or keyword_count >= 3
    return TextStrength(
        character_count=character_count,
        word_count=word_count,
        engineering_keyword_count=keyword_count,
        dimension_unit_pattern_count=dimension_count,
        strong_text=strong_text,
    )


def measure_image_strength(page: object) -> ImageStrength:
    page_width = float(getattr(page, "width", 0.0) or 0.0)
    page_height = float(getattr(page, "height", 0.0) or 0.0)
    page_area = max(page_width * page_height, 1.0)
    images = list(getattr(page, "images", []) or [])

    coverages = []
    for image in images:
        try:
            x0 = float(image.get("x0", 0.0))
            x1 = float(image.get("x1", x0))
            y0 = float(image.get("y0", 0.0))
            y1 = float(image.get("y1", y0))
        except (AttributeError, TypeError, ValueError):
            continue
        area = max(x1 - x0, 0.0) * max(y1 - y0, 0.0)
        coverages.append(max(0.0, min(area / page_area, 1.0)))

    largest = max(coverages, default=0.0)
    total = min(sum(coverages), 1.0)
    large_image = largest >= 0.60 or total >= 0.75
    return ImageStrength(
        image_count=len(images),
        largest_image_coverage=round(largest, 4),
        total_image_coverage=round(total, 4),
        large_image=large_image,
    )


def classify_page(*, text_strength: TextStrength, image_strength: ImageStrength) -> str:
    if text_strength.strong_text and not image_strength.large_image:
        return "text_page"
    if not text_strength.strong_text and image_strength.large_image:
        return "image_page"
    if text_strength.strong_text and image_strength.large_image:
        return "hybrid_page"
    return "empty_or_unknown_page"


def method_for_page(page_type: str) -> str:
    if page_type == "text_page":
        return "text"
    if page_type == "image_page":
        return "ocr"
    if page_type == "hybrid_page":
        return "mixed"
    return "none"


def classify_document(pages: list[PageDetection]) -> str:
    if not pages:
        return "unreadable_pdf"

    text_count = sum(1 for page in pages if page.page_type == "text_page")
    image_count = sum(1 for page in pages if page.page_type == "image_page")
    hybrid_count = sum(1 for page in pages if page.page_type == "hybrid_page")
    readable_count = text_count + image_count + hybrid_count

    if readable_count == 0:
        return "unreadable_pdf"
    if hybrid_count or (text_count and image_count):
        return "hybrid_pdf"
    if image_count and not text_count:
        return "scanned_image_pdf"
    return "text_vector_pdf"

