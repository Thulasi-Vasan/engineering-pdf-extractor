from __future__ import annotations

import json
import re
import shutil
from pathlib import Path
from typing import Any
from uuid import uuid4

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from .agent import extract_pdf


API_OUTPUT_ROOT = Path("outputs") / "api-runs"
ALLOWED_ARTIFACTS = {
    "page_detection.json",
    "raw_extraction.json",
    "structured_engineering_data.json",
    "llm_final_engineering_data.json",
    "extraction_report.md",
}

app = FastAPI(
    title="RFQ Drawing Extractor API",
    version="0.1.0",
    description="Synchronous API wrapper for engineering PDF extraction.",
)


class ArtifactPaths(BaseModel):
    page_detection: str
    raw_extraction: str
    structured_data: str
    final_json: str | None = None
    report: str


class ExtractResponse(BaseModel):
    run_id: str
    status: str = "success"
    final_json: dict[str, Any] | None = None
    artifacts: ArtifactPaths
    warnings: list[str] = Field(default_factory=list)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/extract", response_model=ExtractResponse)
def extract_pdf_endpoint(
    file: UploadFile = File(...),
    use_llm_final_json: bool = Form(True),
    use_vision_dimensions: bool = Form(False),
    llm_final_model: str | None = Form(None),
    vision_model: str | None = Form(None),
) -> ExtractResponse:
    if not file.filename or Path(file.filename).suffix.casefold() != ".pdf":
        raise HTTPException(status_code=400, detail="Upload must be a PDF file.")

    run_id = str(uuid4())
    run_dir = (API_OUTPUT_ROOT / run_id).resolve()
    upload_dir = run_dir / "upload"
    output_dir = run_dir / "outputs"
    upload_dir.mkdir(parents=True, exist_ok=True)
    output_dir.mkdir(parents=True, exist_ok=True)

    uploaded_pdf = upload_dir / _safe_filename(file.filename)
    try:
        with uploaded_pdf.open("wb") as destination:
            shutil.copyfileobj(file.file, destination)
    finally:
        file.file.close()

    try:
        result = extract_pdf(
            uploaded_pdf,
            output_dir=output_dir,
            use_vision_dimensions=use_vision_dimensions,
            vision_model=_blank_to_none(vision_model),
            use_llm_final_json=use_llm_final_json,
            llm_final_model=_blank_to_none(llm_final_model),
        )
    except (FileNotFoundError, ValueError, RuntimeError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    final_json = _load_json(result.final_json_path) if result.final_json_path else None
    warnings = _response_warnings(final_json)
    return ExtractResponse(
        run_id=run_id,
        status="success",
        final_json=final_json,
        artifacts=ArtifactPaths(
            page_detection=_artifact_url(run_id, "page_detection.json"),
            raw_extraction=_artifact_url(run_id, "raw_extraction.json"),
            structured_data=_artifact_url(run_id, "structured_engineering_data.json"),
            final_json=_artifact_url(run_id, "llm_final_engineering_data.json") if result.final_json_path else None,
            report=_artifact_url(run_id, "extraction_report.md"),
        ),
        warnings=warnings,
    )


@app.get("/artifacts/{run_id}/{filename}")
def get_artifact(run_id: str, filename: str) -> FileResponse:
    if not re.fullmatch(r"[0-9a-fA-F-]{36}", run_id):
        raise HTTPException(status_code=404, detail="Artifact not found.")
    if filename not in ALLOWED_ARTIFACTS:
        raise HTTPException(status_code=404, detail="Artifact not found.")

    artifact_path = (API_OUTPUT_ROOT / run_id / "outputs" / filename).resolve()
    output_root = API_OUTPUT_ROOT.resolve()
    if output_root not in artifact_path.parents or not artifact_path.is_file():
        raise HTTPException(status_code=404, detail="Artifact not found.")
    return FileResponse(artifact_path)


def _safe_filename(filename: str) -> str:
    path = Path(filename)
    stem = re.sub(r"[^A-Za-z0-9._-]+", "-", path.stem).strip("-") or "upload"
    return f"{stem}.pdf"


def _blank_to_none(value: str | None) -> str | None:
    if value is None:
        return None
    value = value.strip()
    return value or None


def _load_json(path: str | None) -> dict[str, Any] | None:
    if not path:
        return None
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _response_warnings(final_json: dict[str, Any] | None) -> list[str]:
    if not final_json:
        return ["LLM final JSON was not generated for this request."]
    warnings = list(final_json.get("warnings") or [])
    if final_json.get("status") == "failed":
        warnings.append("LLM final JSON generation failed; see final_json.warnings for details.")
    return warnings


def _artifact_url(run_id: str, filename: str) -> str:
    return f"/artifacts/{run_id}/{filename}"
