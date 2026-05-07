from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field


PageType = Literal["text_page", "image_page", "hybrid_page", "empty_or_unknown_page"]
PdfType = Literal["text_vector_pdf", "scanned_image_pdf", "hybrid_pdf", "unreadable_pdf"]
ExtractionMethod = Literal["text", "ocr", "mixed", "none"]
SourceType = Literal["text", "ocr", "mixed", "inferred", "vision_llm"]
ConfidenceLabel = Literal["high", "medium", "low"]


class RunMetadata(BaseModel):
    input_path: str
    file_name: str
    file_size_bytes: int
    run_id: str
    output_dir: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class TextStrength(BaseModel):
    character_count: int = 0
    word_count: int = 0
    engineering_keyword_count: int = 0
    dimension_unit_pattern_count: int = 0
    strong_text: bool = False


class ImageStrength(BaseModel):
    image_count: int = 0
    largest_image_coverage: float = 0.0
    total_image_coverage: float = 0.0
    large_image: bool = False


class PageDetection(BaseModel):
    page_number: int
    page_type: PageType
    extraction_method: ExtractionMethod
    text_strength: TextStrength
    image_strength: ImageStrength
    ocr_used: bool = False
    native_text_preview: str = ""
    native_text: str = Field(default="", exclude=True)
    warnings: list[str] = Field(default_factory=list)


class PageDetectionResult(BaseModel):
    pdf_type: PdfType
    page_count: int
    pages: list[PageDetection]
    document_warnings: list[str] = Field(default_factory=list)


class WordBox(BaseModel):
    text: str
    x0: float
    top: float
    x1: float
    bottom: float
    source: Literal["text", "ocr"]
    confidence: float = 1.0


class TableExtraction(BaseModel):
    source: str
    rows: list[list[str]]
    page: int | None = None
    confidence: float | None = None


class TextractLine(BaseModel):
    text: str
    confidence: float
    left: float
    top: float
    width: float
    height: float


class PageExtraction(BaseModel):
    page_number: int
    page_type: PageType
    extraction_method: ExtractionMethod
    text: str = ""
    raw_text: str = ""
    page_width: float
    page_height: float
    words: list[WordBox] = Field(default_factory=list)
    tables: list[TableExtraction] = Field(default_factory=list)
    textract_lines: list[TextractLine] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class RawExtractionResult(BaseModel):
    pdf_type: PdfType
    page_count: int
    pages: list[PageExtraction]
    document_warnings: list[str] = Field(default_factory=list)


class ExtractedField(BaseModel):
    value: str
    source: SourceType = "text"
    page: int | None = None
    confidence: ConfidenceLabel = "medium"
    evidence: str = ""
    warnings: list[str] = Field(default_factory=list)


class BomComponent(BaseModel):
    item_no: str
    component_name: str
    quantity: int | None = None
    material: str | None = None
    note: str = ""
    category: str = ""
    source: SourceType = "text"
    page: int | None = None
    confidence: ConfidenceLabel = "medium"
    evidence: str = ""
    warnings: list[str] = Field(default_factory=list)


class DimensionCandidate(BaseModel):
    value: float
    unit: Literal["mm", "inch", "degree", "unknown"] = "unknown"
    imperial_value: float | None = None
    dimension_type: str = "linear"
    role: str = "unknown"
    role_confidence: ConfidenceLabel = "low"
    source: SourceType = "text"
    page: int | None = None
    confidence: ConfidenceLabel = "medium"
    evidence: str = ""
    warnings: list[str] = Field(default_factory=list)


class ConnectionCandidate(BaseModel):
    label: str = ""
    size: str = ""
    connection_type: str = ""
    option: bool = False
    source: SourceType = "text"
    page: int | None = None
    confidence: ConfidenceLabel = "medium"
    evidence: str = ""
    warnings: list[str] = Field(default_factory=list)


class EnvelopeAxisMeasurement(BaseModel):
    value: float | None = None
    unit: Literal["mm", "inch", "unknown"] = "unknown"
    imperial_value: float | None = None
    source: SourceType = "vision_llm"
    page: int | None = None
    confidence: ConfidenceLabel = "low"
    evidence: str = ""
    warnings: list[str] = Field(default_factory=list)


class EnvelopeCalculation(BaseModel):
    value: float | None = None
    unit: str = ""
    imperial_value: float | None = None
    imperial_unit: str = ""
    formula: str = ""
    source: SourceType = "inferred"
    confidence: ConfidenceLabel = "low"
    evidence: str = ""
    warnings: list[str] = Field(default_factory=list)


class OverallEnvelope(BaseModel):
    length: EnvelopeAxisMeasurement | None = None
    breadth: EnvelopeAxisMeasurement | None = None
    height: EnvelopeAxisMeasurement | None = None
    surface_area: EnvelopeCalculation | None = None
    volume: EnvelopeCalculation | None = None
    source: SourceType = "vision_llm"
    confidence: ConfidenceLabel = "low"
    evidence: str = ""
    warnings: list[str] = Field(default_factory=list)


class StructuredEngineeringData(BaseModel):
    title_block: dict[str, ExtractedField] = Field(default_factory=dict)
    drawing_type: ExtractedField | None = None
    units: ExtractedField | None = None
    standards: list[ExtractedField] = Field(default_factory=list)
    bom_components: list[BomComponent] = Field(default_factory=list)
    dimensions: list[DimensionCandidate] = Field(default_factory=list)
    connections: list[ConnectionCandidate] = Field(default_factory=list)
    notes: list[ExtractedField] = Field(default_factory=list)
    drawing_structure: dict[str, Any] = Field(default_factory=dict)
    tolerances_gdnt: list[ExtractedField] = Field(default_factory=list)
    process_requirements: list[ExtractedField] = Field(default_factory=list)
    overall_envelope: OverallEnvelope = Field(default_factory=OverallEnvelope)
    semantic_summary: str = ""
    warnings: list[str] = Field(default_factory=list)


class ExtractionRunResult(BaseModel):
    metadata: RunMetadata
    page_detection_path: str
    raw_extraction_path: str
    structured_data_path: str
    report_path: str
    page_detection: PageDetectionResult
    raw_extraction: RawExtractionResult
    structured_data: StructuredEngineeringData


def write_json(path: Path, payload: BaseModel) -> None:
    path.write_text(payload.model_dump_json(indent=2), encoding="utf-8")
