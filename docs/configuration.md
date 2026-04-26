# Configuration

Configuration is intentionally simple. Most runtime behavior comes from:

- environment variables
- the selected quality profile
- whether native Tesseract OCR is installed
- whether OpenAI credentials are available

## Environment Variables

| Variable | Default | Purpose |
| --- | --- | --- |
| `OPENAI_API_KEY` | unset | Enables GPT generation, ambiguous-boundary review, and risky-step verification. |
| `OPENAI_MODEL` | `gpt-5.5` | Model used for OpenAI-backed generation and review. |
| `VIDEO2SOP_INPUT_PRICE_PER_1M` | `5.00` | Input token price used for cost estimation. |
| `VIDEO2SOP_OUTPUT_PRICE_PER_1M` | `30.00` | Output token price used for cost estimation. |
| `VIDEO2SOP_LOW_DETAIL_IMAGE_TOKENS` | `85` | Estimated low-detail image token count used in cost estimation. |
| `VIDEO2SOP_TEXT_INPUT_TOKENS_PER_EVENT` | `220` | Estimated text input tokens per event used in cost estimation. |
| `VIDEO2SOP_OUTPUT_TOKENS_PER_STEP` | `90` | Estimated output tokens per step used in cost estimation. |
| `VIDEO2SOP_FIXED_PROMPT_TOKENS_PER_CALL` | `900` | Estimated fixed prompt overhead per call used in cost estimation. |

## Quality Profiles

Profiles are defined in [pipeline/config.py](<G:/My Drive/Video-to-SOP/pipeline/config.py>) through the `QualityProfile` dataclass.

Each profile defines:

- `metric_interval_seconds`
- `max_metric_frames`
- `frame_interval_seconds`
- `max_extracted_frames`
- `max_selected_frames`
- `max_ocr_frames`
- `max_events`
- `max_steps`
- `batch_size`
- `max_gpt_calls`
- `verify_risky_limit`
- `include_context_images`
- `ambiguous_boundary_reviews`

### `Balanced`

Default profile intended for real usage:

- `metric_interval_seconds = 1.0`
- `max_metric_frames = 2800`
- `frame_interval_seconds = 4.5`
- `max_extracted_frames = 850`
- `max_selected_frames = 80`
- `max_ocr_frames = 60`
- `max_events = 40`
- `max_steps = 40`
- `batch_size = 9`
- `max_gpt_calls = 6`
- `verify_risky_limit = 24`
- `include_context_images = True`
- `ambiguous_boundary_reviews = 8`

Use when:

- you want the current best default balance of quality and cost
- the recording is moderately complex
- you want cleanup and boundary review to have enough evidence

### `Lowest cost`

Cheapest profile:

- `metric_interval_seconds = 2.0`
- `max_metric_frames = 1400`
- `frame_interval_seconds = 6.0`
- `max_extracted_frames = 500`
- `max_selected_frames = 50`
- `max_ocr_frames = 40`
- `max_events = 28`
- `max_steps = 30`
- `batch_size = 10`
- `max_gpt_calls = 4`
- `verify_risky_limit = 12`
- `include_context_images = False`
- `ambiguous_boundary_reviews = 0`

Use when:

- you are experimenting
- the workflow is simple
- you want to minimize image and model usage

### `Highest accuracy`

Most evidence-heavy bounded profile:

- `metric_interval_seconds = 1.0`
- `max_metric_frames = 3200`
- `frame_interval_seconds = 3.0`
- `max_extracted_frames = 950`
- `max_selected_frames = 110`
- `max_ocr_frames = 80`
- `max_events = 45`
- `max_steps = 40`
- `batch_size = 8`
- `max_gpt_calls = 8`
- `verify_risky_limit = 32`
- `include_context_images = True`
- `ambiguous_boundary_reviews = 16`

Use when:

- the workflow is denser
- you want stronger local evidence coverage
- you accept higher bounded model cost

## Cost Estimation

The UI shows a rough maximum API estimate before a job starts.

The estimator uses:

- profile call caps
- estimated low-detail image token counts
- estimated event text token counts
- estimated output tokens
- current configured pricing defaults

The estimate is intentionally rough and conservative. Actual billed usage depends on:

- model behavior
- the number of ambiguous-boundary review calls that actually happen
- the number of risky verification rows
- image tokenization details
- retries or fallbacks

The returned estimate includes:

- `model`
- `profile`
- `max_calls`
- `image_count`
- `input_tokens`
- `output_tokens`
- `estimated_cost_usd`
- `pricing_note`

## OCR Configuration

OCR is required for local draft quality when OpenAI vision is unavailable. The code resolves native Tesseract in this order:

1. `TESSERACT_CMD`
2. PATH lookup for `tesseract`
3. `C:\Program Files\Tesseract-OCR\tesseract.exe`
4. `C:\Program Files (x86)\Tesseract-OCR\tesseract.exe`

What is included in the repo:

- the Python dependency `pytesseract`
- OCR preprocessing and OCR orchestration code

What is not bundled into the repo:

- the native Tesseract executable
- trained data files installed by the operating system package

Why it is not vendored:

- native Tesseract is a separate system binary
- bundling it into a Python repo would make the repository heavier, less portable, and harder to maintain across Windows setups

If native Tesseract is found:

- OCR preprocessing images are written under `jobs/{job_id}/ocr`
- OCR runs with multiple fast segmentation modes
- the stronger result is kept

If native Tesseract is missing:

- OCR text stays empty
- production SOP generation is blocked unless OpenAI vision is configured
- explicit diagnostic drafts remain possible

Recommended Windows install:

```powershell
winget install UB-Mannheim.TesseractOCR
```

Optional local override:

```powershell
$env:TESSERACT_CMD="C:\Program Files\Tesseract-OCR\tesseract.exe"
```

Check prerequisites:

```powershell
python scripts\check_prereqs.py
```

## Upload Limit

Streamlit upload size is configured in:

[.streamlit/config.toml](<G:/My Drive/Video-to-SOP/.streamlit/config.toml>)

Current value:

```toml
[server]
maxUploadSize = 2048
```

This allows uploads up to 2048 MB.

## Runtime Modes

### Production Vision

OpenAI is used for:

- compact step generation
- ambiguous-boundary review
- risky-step verification

Cleanup, ordering, chronology repair, and DOCX export remain local and deterministic.

### OCR Draft

When OpenAI is unavailable but OCR produces text, the app can generate an OCR draft using:

- local segmentation
- local OCR when available
- local fallback step generation
- deterministic cleanup and quality scoring

### Diagnostic Draft

When neither OpenAI vision nor OCR text is available, the app marks output as a diagnostic draft and blocks `demo_ready`.

## Public Repository Safety

The repository is configured to be safe for public GitHub use if local secrets and generated artifacts stay ignored.

Ignored by default:

- `.env`
- `.env.*`
- `.streamlit/secrets.toml`
- `jobs/`
- `storage/*.sqlite3`
- logs
- caches
- local virtual environments

Reference files:

- [.gitignore](<G:/My Drive/Video-to-SOP/.gitignore>)
- [.env.example](<G:/My Drive/Video-to-SOP/.env.example>)
