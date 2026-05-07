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
