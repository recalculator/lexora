# Fine-Tuning Guide for Lexora LLM Tasks

This document explains how to fine-tune OpenAI-compatible models for Lexora's explain endpoint to improve JSON schema adherence and response consistency.

## Overview

Fine-tuning improves:
- **Schema adherence**: Better compliance with Pydantic JSON schemas
- **Response consistency**: More predictable formatting and structure
- **Style**: More consistent explanation style across clauses

Fine-tuning does NOT:
- Add legal knowledge (that comes from prompts)
- Improve factual accuracy (grounding is still required)
- Replace retrieval (RAG still needed for context)

## Dataset Creation

### Option 1: Export from Prompt Logs

If you have existing explain endpoint usage:

```bash
cd backend
python -m app.scripts.export_finetune_dataset
```

This exports prompts/responses from the `prompt_logs` table to `ml/finetune_explain.jsonl` in OpenAI chat format.

### Option 2: Generate Synthetic Dataset

If no prompt logs exist, generate synthetic examples:

```bash
cd ml
python generate_synthetic_explain_dataset.py
```

This creates 60 training examples from curated clause samples.

**Using Teacher Model (Optional):**

To generate higher-quality examples using GPT-4o:

```bash
python generate_synthetic_explain_dataset.py --use-teacher --teacher-model gpt-4o
```

This uses GPT-4o to generate explanations for distillation to GPT-4o-mini.

## Fine-Tuning Process

### Step 1: Upload Dataset

```bash
cd ml
python openai_upload.py --file finetune_explain.jsonl
```

This uploads the JSONL file to OpenAI and saves the file ID to `ml/finetune_file_id.txt`.

### Step 2: Create Fine-Tuning Job

```bash
python openai_finetune.py --model gpt-4o-mini --suffix lexora-explain
```

This creates a fine-tuning job. The job ID is saved to `ml/finetune_job_id.txt`.

### Step 3: Monitor Job Status

```bash
python openai_check_job.py
```

Or watch until completion:

```bash
python openai_check_job.py --watch
```

### Step 4: Get Fine-Tuned Model Name

Once the job completes, the fine-tuned model name is saved to `ml/finetune_model_name.txt`.

## Using Fine-Tuned Model

### Set Environment Variable

```bash
export OPENAI_MODEL=ft:gpt-4o-mini-org:lexora-explain:abc123...
```

Or in `.env`:

```
OPENAI_MODEL=ft:gpt-4o-mini-org:lexora-explain:abc123...
```

### Verify Model Usage

The LLM client (`backend/app/services/llm_client.py`) automatically uses `OPENAI_MODEL` if set, otherwise defaults to `gpt-4o-mini`.

Check logs to confirm which model is being called.

## Fine-Tuning for Other Tasks

Currently, fine-tuning is set up for the explain endpoint. To fine-tune playbook or redlines:

1. Update `export_finetune_dataset.py` to filter by `kind="playbook"` or `kind="redlines"`
2. Generate synthetic datasets for those tasks
3. Follow the same upload/finetune process

## Cost Considerations

- Fine-tuning cost: ~$0.008 per 1K tokens (training)
- Fine-tuned model inference: Same as base model pricing
- Dataset size: 60 examples is minimal; 200+ recommended for production

## Evaluation

After fine-tuning, compare:
- Schema validation success rate (should increase)
- Response consistency (manual review)
- User feedback on explanation quality

No automated evaluation metrics are provided; manual review is recommended.

## Troubleshooting

**"File ID not found"**: Run `openai_upload.py` first.

**"Job ID not found"**: Run `openai_finetune.py` first.

**"OPENAI_API_KEY not set"**: Set in `.env` or environment.

**Fine-tuning fails**: Check file format (must be valid JSONL with "messages" array).

## Notes

- Fine-tuned models are tied to your OpenAI account
- Model names follow pattern: `ft:gpt-4o-mini-org:lexora-explain:{timestamp}`
- Fine-tuning takes 10-60 minutes depending on dataset size
- Base model must support fine-tuning (gpt-4o-mini, gpt-3.5-turbo, etc.)
