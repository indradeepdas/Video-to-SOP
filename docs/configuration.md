# Configuration

Most configuration is local and controlled by environment variables or the Streamlit quality profile.

## Environment Variables

| Variable | Default | Purpose |
| --- | --- | --- |
| `OPENAI_API_KEY` | unset | Enables GPT generation and verification. |
| `OPENAI_MODEL` | `gpt-5.5` | Model used for generation and verification. |
| `VIDEO2SOP_INPUT_PRICE_PER_1M` | `5.00` | Input token price used for estimates. |
| `VIDEO2SOP_OUTPUT_PRICE_PER_1M` | `30.00` | Output token price used for estimates. |
| `VIDEO2SOP_LOW_DETAIL_IMAGE_TOKENS` | `85` | Estimated low-detail image token count. |
| `VIDEO2SOP_TEXT_INPUT_TOKENS_PER_EVENT` | `220` | Estimated event text input tokens. |
| `VIDEO2SOP_OUTPUT_TOKENS_PER_STEP` | `90` | Estimated output tokens per step. |
| `VIDEO2SOP_FIXED_PROMPT_TOKENS_PER_CALL` | `900` | Estimated prompt overhead per model call. |

## Quality Profiles

Profiles are defined in `pipeline/config.py`.

### Balanced

Default profile for hobbyist use:

- 4.5 second frame interval
- 850 extracted frame cap
- 80 selected frame cap
- 60 OCR frame cap
- 40 event cap
- 40 final step cap
- 9 events per generation batch
- 6 GPT call cap
- 24 risky verification rows

### Lowest cost

Uses fewer frames and fewer model calls. Good for short recordings or early experiments.

### Highest accuracy

Uses more local evidence and more screenshot context. Better for complex recordings, with higher expected API usage.

## Upload Limit

Streamlit upload size is configured in:

```text
.streamlit/config.toml
```

Current value:

```toml
[server]
maxUploadSize = 2048
```

This allows uploads up to 2048 MB.

## Cost Estimate

The app shows a rough maximum estimate before running a job. It is based on profile caps, estimated low-detail image tokens, and model token prices.

The estimate is intentionally approximate. Actual billing depends on the OpenAI API response, model behavior, image tokenization, retries, and whether fallback mode is used.

## Tesseract OCR

Tesseract is optional but recommended.

If installed, make sure `tesseract.exe` is on PATH. The app detects availability with `shutil.which("tesseract")`.

If missing, jobs continue with empty OCR text and low confidence where appropriate.
