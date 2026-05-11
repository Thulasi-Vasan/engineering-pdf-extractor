from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field


PageType = Literal["text_page", "image_page", "hybrid_page", "empty_or_unknown_page"]
PdfType = Literal["text_vector_pdf", "scanned_image_pdf", "hybrid_pdf", "unreadable_pdf"]
ExtractionMethod = Literal["text", "ocr", "mixed", "none"]
SourceType = Literal["text", "ocr", "mixed", "inferred", "vision_llm"]
ConfidenceLabel = Literal["high", "medium", "low", "review"]


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


class TextLine(BaseModel):
    text: str
    normalized_text: str = ""
    x0: float
    top: float
    x1: float
    bottom: float
    page: int | None = None
    source: Literal["text", "ocr", "mixed"] = "text"
    confidence: float = 1.0
    warnings: list[str] = Field(default_factory=list)


class PageExtraction(BaseModel):
    page_number: int
    page_type: PageType
    extraction_method: ExtractionMethod
    text: str = ""
    raw_text: str = ""
    page_width: float
    page_height: float
    words: list[WordBox] = Field(default_factory=list)
    reconstructed_lines: list[TextLine] = Field(default_factory=list)
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
    secondary_value: float | None = None
    imperial_value: float | None = None
    dimension_type: str = "linear"
    quantity: int | None = None
    angle_value: float | None = None
    angle_unit: Literal["degree", "unknown"] = "unknown"
    role: str = "unknown"
    role_confidence: ConfidenceLabel = "low"
    raw_callout: str = ""
    normalized_callout: str = ""
    region_id: str = ""
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


class EngineeringTable(BaseModel):
    table_type: str
    headers: list[str] = Field(default_factory=list)
    rows: list[dict[str, str]] = Field(default_factory=list)
    source: SourceType = "text"
    page: int | None = None
    confidence: ConfidenceLabel = "medium"
    evidence: str = ""
    warnings: list[str] = Field(default_factory=list)


class ThreadRequirement(BaseModel):
    thread_size: str = ""
    pitch: float | None = None
    threads_per_inch: int | None = None
    thread_class: str = ""
    quantity: int | None = None
    minimum_full_threads: int | None = None
    label: str = ""
    relief_note: str = ""
    chart_reference: str = ""
    source_table: str = ""
    source: SourceType = "text"
    page: int | None = None
    region_id: str = ""
    confidence: ConfidenceLabel = "medium"
    evidence: str = ""
    warnings: list[str] = Field(default_factory=list)


class DrawingRegion(BaseModel):
    region_id: str
    page: int
    region_type: str
    label: str = ""
    x0: float | None = None
    top: float | None = None
    x1: float | None = None
    bottom: float | None = None
    source: SourceType = "inferred"
    confidence: ConfidenceLabel = "low"
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
    engineering_tables: list[EngineeringTable] = Field(default_factory=list)
    thread_requirements: list[ThreadRequirement] = Field(default_factory=list)
    dimensions: list[DimensionCandidate] = Field(default_factory=list)
    review_dimensions: list[DimensionCandidate] = Field(default_factory=list)
    connections: list[ConnectionCandidate] = Field(default_factory=list)
    notes: list[ExtractedField] = Field(default_factory=list)
    drawing_regions: list[DrawingRegion] = Field(default_factory=list)
    drawing_structure: dict[str, Any] = Field(default_factory=dict)
    tolerances_gdnt: list[ExtractedField] = Field(default_factory=list)
    process_requirements: list[ExtractedField] = Field(default_factory=list)
    manufacturing_requirements: list[ExtractedField] = Field(default_factory=list)
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
