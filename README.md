## RFQ Drawing Extractor Demo

Run deterministic extraction:

```bash
uv run python main.py "docs/RC2-100&140 Model A&B Compressor MCS Outline.pdf"
```

Run deterministic extraction plus AWS Bedrock vision LLM dimension recovery:

```bash
AWS_ACCESS_KEY_ID=... AWS_SECRET_ACCESS_KEY=... AWS_REGION=us-east-1 uv run python main.py "docs/RC2-100&140 Model A&B Compressor MCS Outline.pdf" --vision-dimensions
```

Optional Bedrock vision model override:

```bash
uv run python main.py "docs/RC2-100&140 Model A&B Compressor MCS Outline.pdf" --vision-dimensions --vision-model anthropic.claude-3-5-sonnet-20241022-v2:0
```

The AWS account must have Amazon Bedrock model access enabled in the selected region.

The vision path renders PDF pages as images and asks the model for visible drawing dimensions only. Text/parser dimensions are kept as exact evidence; vision-only dimensions are added with `source: "vision_llm"`, and matching text plus vision dimensions are merged with `source: "mixed"`.

## FastAPI Backend

Run the backend:

```bash
uv run uvicorn rfq_drawing_extractor.api:app --reload --host 0.0.0.0 --port 8000
```

Health check:

```bash
curl http://127.0.0.1:8000/health
```

Upload and extract a PDF:

```bash
curl -X POST http://127.0.0.1:8000/extract \
  -F "file=@docs/MCP02498.pdf" \
  -F "use_llm_final_json=true"
```

The API returns the final downstream JSON from `llm_final_engineering_data.json` plus artifact links for page detection, raw extraction, structured extraction, final JSON, and report files.

Recommended `.env` for Bedrock final JSON:

```env
AWS_REGION=us-east-1
AWS_DEFAULT_REGION=us-east-1
BEDROCK_FINALIZER_MODEL=global.anthropic.claude-sonnet-4-6
```
