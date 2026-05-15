from __future__ import annotations

import re
from pathlib import Path
from uuid import uuid4

from .detection import detect_pdf_pages
from .engineering_parser import parse_engineering_data, refresh_semantic_summary
from .extraction import extract_raw_content
from .llm_finalizer import finalize_engineering_data_with_llm
from .models import ExtractionRunResult, RunMetadata, write_json
from .report import build_markdown_report
from .vision_dimensions import augment_dimensions_with_vision_llm


def extract_pdf(
    pdf_path: Path,
    output_dir: Path | None = None,
    *,
    use_vision_dimensions: bool = False,
    vision_model: str | None = None,
    use_llm_final_json: bool = False,
    llm_final_model: str | None = None,
) -> ExtractionRunResult:
    pdf_path = pdf_path.expanduser().resolve()
    _validate_pdf(pdf_path)

    run_id = str(uuid4())
    output_dir = output_dir or Path("outputs") / _safe_stem(pdf_path.stem)
    output_dir = output_dir.expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    metadata = RunMetadata(
        input_path=str(pdf_path),
        file_name=pdf_path.name,
        file_size_bytes=pdf_path.stat().st_size,
        run_id=run_id,
        output_dir=str(output_dir),
    )

    page_detection = detect_pdf_pages(pdf_path)
    raw_extraction = extract_raw_content(pdf_path, page_detection)
    structured_data = parse_engineering_data(raw_extraction)
    if use_vision_dimensions:
        augment_dimensions_with_vision_llm(
            pdf_path,
            raw_extraction,
            structured_data,
            model=vision_model,
        )
        refresh_semantic_summary(structured_data)

    page_detection_path = output_dir / "page_detection.json"
    raw_extraction_path = output_dir / "raw_extraction.json"
    structured_data_path = output_dir / "structured_engineering_data.json"
    llm_final_data_path = output_dir / "llm_final_engineering_data.json"
    report_path = output_dir / "extraction_report.md"

    write_json(page_detection_path, page_detection)
    write_json(raw_extraction_path, raw_extraction)
    write_json(structured_data_path, structured_data)
    llm_final_data = None
    llm_final_path_value = None
    if use_llm_final_json:
        llm_final_data = finalize_engineering_data_with_llm(
            pdf_path,
            page_detection,
            raw_extraction,
            structured_data,
            model=llm_final_model,
        )
        write_json(llm_final_data_path, llm_final_data)
        llm_final_path_value = str(llm_final_data_path)

    result = ExtractionRunResult(
        metadata=metadata,
        page_detection_path=str(page_detection_path),
        raw_extraction_path=str(raw_extraction_path),
        structured_data_path=str(structured_data_path),
        final_json_path=llm_final_path_value,
        report_path=str(report_path),
        llm_final_data_path=llm_final_path_value,
        page_detection=page_detection,
        raw_extraction=raw_extraction,
        structured_data=structured_data,
        llm_final_data=llm_final_data,
    )
    report_path.write_text(build_markdown_report(result), encoding="utf-8")
    return result


def _validate_pdf(pdf_path: Path) -> None:
    if not pdf_path.exists():
        raise FileNotFoundError(f"PDF does not exist: {pdf_path}")
    if not pdf_path.is_file():
        raise ValueError(f"Path is not a file: {pdf_path}")
    if pdf_path.suffix.casefold() != ".pdf":
        raise ValueError(f"Only PDF files are supported, got: {pdf_path.name}")
    if pdf_path.stat().st_size <= 0:
        raise ValueError(f"PDF is empty: {pdf_path}")


def _safe_stem(stem: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9]+", "-", stem).strip("-")
    return cleaned or "pdf-extraction"
