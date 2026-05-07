from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

from .models import TableExtraction, TextractLine, WordBox


class TextractPageResult:
    def __init__(
        self,
        *,
        text: str = "",
        words: list[WordBox] | None = None,
        lines: list[TextractLine] | None = None,
        tables: list[TableExtraction] | None = None,
        warnings: list[str] | None = None,
    ) -> None:
        self.text = text
        self.words = words or []
        self.lines = lines or []
        self.tables = tables or []
        self.warnings = warnings or []


def analyze_page_with_textract(pdf_path: Path, page_number: int) -> TextractPageResult:
    load_dotenv()

    missing = [
        name
        for name in ("AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "AWS_REGION")
        if not os.getenv(name)
    ]
    if missing:
        return TextractPageResult(
            warnings=[
                "Textract OCR was required but AWS configuration is missing: "
                + ", ".join(missing)
            ]
        )

    try:
        import boto3
        import fitz
    except ImportError as exc:
        return TextractPageResult(warnings=[f"Textract OCR dependency is missing: {exc.name}"])

    try:
        image_bytes = _render_page_to_png(pdf_path, page_number, fitz_module=fitz)
        client = boto3.client(
            "textract",
            region_name=os.getenv("AWS_REGION"),
            aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
            aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY"),
            aws_session_token=os.getenv("AWS_SESSION_TOKEN") or None,
        )
        response = client.analyze_document(
            Document={"Bytes": image_bytes},
            FeatureTypes=["TABLES", "LAYOUT"],
        )
    except Exception as exc:
        return TextractPageResult(warnings=[f"Textract OCR failed: {exc}"])

    return _parse_textract_response(response)


def _render_page_to_png(pdf_path: Path, page_number: int, *, fitz_module: Any) -> bytes:
    document = fitz_module.open(str(pdf_path))
    try:
        page = document.load_page(page_number - 1)
        matrix = fitz_module.Matrix(2.0, 2.0)
        pixmap = page.get_pixmap(matrix=matrix, alpha=False)
        return pixmap.tobytes("png")
    finally:
        document.close()


def _parse_textract_response(response: dict[str, Any]) -> TextractPageResult:
    blocks = response.get("Blocks", []) or []
    block_by_id = {block.get("Id"): block for block in blocks if block.get("Id")}

    lines: list[TextractLine] = []
    words: list[WordBox] = []
    text_lines: list[str] = []

    for block in blocks:
        block_type = block.get("BlockType")
        text = str(block.get("Text", "")).strip()
        geometry = block.get("Geometry", {}).get("BoundingBox", {})
        confidence = float(block.get("Confidence", 0.0) or 0.0)
        if block_type == "LINE" and text:
            text_lines.append(text)
            lines.append(
                TextractLine(
                    text=text,
                    confidence=confidence,
                    left=float(geometry.get("Left", 0.0) or 0.0),
                    top=float(geometry.get("Top", 0.0) or 0.0),
                    width=float(geometry.get("Width", 0.0) or 0.0),
                    height=float(geometry.get("Height", 0.0) or 0.0),
                )
            )
        elif block_type == "WORD" and text:
            left = float(geometry.get("Left", 0.0) or 0.0)
            top = float(geometry.get("Top", 0.0) or 0.0)
            width = float(geometry.get("Width", 0.0) or 0.0)
            height = float(geometry.get("Height", 0.0) or 0.0)
            words.append(
                WordBox(
                    text=text,
                    x0=left,
                    top=top,
                    x1=left + width,
                    bottom=top + height,
                    source="ocr",
                    confidence=confidence / 100.0,
                )
            )

    return TextractPageResult(
        text="\n".join(text_lines),
        words=words,
        lines=lines,
        tables=_parse_tables(blocks, block_by_id),
    )


def _parse_tables(blocks: list[dict[str, Any]], block_by_id: dict[str, dict[str, Any]]) -> list[TableExtraction]:
    tables: list[TableExtraction] = []
    for block in blocks:
        if block.get("BlockType") != "TABLE":
            continue
        cell_ids = _child_ids(block)
        cells = [
            block_by_id[cell_id]
            for cell_id in cell_ids
            if block_by_id.get(cell_id, {}).get("BlockType") == "CELL"
        ]
        if not cells:
            continue
        max_row = max(int(cell.get("RowIndex", 1) or 1) for cell in cells)
        max_col = max(int(cell.get("ColumnIndex", 1) or 1) for cell in cells)
        rows = [["" for _ in range(max_col)] for _ in range(max_row)]
        confidences = []
        for cell in cells:
            row = int(cell.get("RowIndex", 1) or 1) - 1
            col = int(cell.get("ColumnIndex", 1) or 1) - 1
            rows[row][col] = _cell_text(cell, block_by_id)
            if cell.get("Confidence") is not None:
                confidences.append(float(cell.get("Confidence", 0.0) or 0.0))
        confidence = (sum(confidences) / len(confidences) / 100.0) if confidences else None
        tables.append(TableExtraction(source="textract", rows=rows, confidence=confidence))
    return tables


def _child_ids(block: dict[str, Any]) -> list[str]:
    ids: list[str] = []
    for relationship in block.get("Relationships", []) or []:
        if relationship.get("Type") == "CHILD":
            ids.extend(str(item) for item in relationship.get("Ids", []) or [])
    return ids


def _cell_text(cell: dict[str, Any], block_by_id: dict[str, dict[str, Any]]) -> str:
    parts = []
    for child_id in _child_ids(cell):
        child = block_by_id.get(child_id, {})
        if child.get("BlockType") == "WORD" and child.get("Text"):
            parts.append(str(child["Text"]))
        elif child.get("BlockType") == "SELECTION_ELEMENT":
            parts.append(str(child.get("SelectionStatus", "")))
    return " ".join(parts).strip()

