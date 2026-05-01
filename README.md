# Video2SOP Fast Mode

Video2SOP is a local Streamlit application that turns a screen recording into a screenshot-backed SOP DOCX. It is built for process documentation, not generic video analysis.

The current implementation is local-first:

- OpenCV extracts dense frames for metric scoring and selected frames for evidence.
- A deterministic segmentation engine detects screen-state boundaries.
- OCR enriches segment evidence when native Tesseract is installed. The app now resolves `TESSERACT_CMD`, PATH, and common Windows install paths.
- Rule-based classification and deterministic cleanup reduce noise, passive filler, and weak duplicates.
- OpenAI vision is required for production-grade SOP wording. Without OpenAI, the app can create an OCR draft when OCR text is available or a diagnostic draft when no semantic evidence is available.
- `.env` and optional Streamlit secrets are loaded automatically, so first-time users do not need to pre-load shell variables manually.
- The final DOCX includes screenshots, confidence indicators, timeline-safe phase sections, and a cleanup quality appendix.

## Product Promise

Turn a process recording into a professional SOP in minutes.

The product is designed to remain honest with and without OpenAI:

- With OpenAI: production vision mode for evidence-backed SOP wording, bounded boundary review, and risky-step verification.
- Without OpenAI but with OCR: OCR draft mode using local text evidence.
- Without OpenAI and without OCR text: diagnostic draft mode only; the document is marked `not_ready`.

## What The App Produces

The generated DOCX includes:

- `SOP: {process_name}` title
- summary, prerequisites, and assumptions
- chronological steps rendered in timeline phase sections
- screenshot evidence for each step
- system, action, expected output, and confidence
- low-confidence review checklist
- cleanup and quality report appendix
- job metadata appendix

The app does not pad weak runs with invented steps. If the recording only supports a short SOP, the output stays short and the document records warnings instead of pretending the process was fully captured.

## What Changed Recently

The codebase now includes the major upgrades shipped over the last two working days:

### 1. Public GitHub Safety

- Added [.gitignore](<G:/My Drive/Video-to-SOP/.gitignore>) for `.env`, `.env.*`, `.streamlit/secrets.toml`, `jobs/`, SQLite files, logs, caches, and local virtual environments.
- Added [.env.example](<G:/My Drive/Video-to-SOP/.env.example>) with placeholders only.
- Updated the repo to assume all secrets are provided by environment variables or ignored local files.

### 2. Adaptive Screen Segmentation

- Added [pipeline/segmentation.py](<G:/My Drive/Video-to-SOP/pipeline/segmentation.py>).
- The pipeline now uses dense frame metrics, adaptive thresholds, hysteresis, screen-state clustering, scroll collapse, and optional GPT review for ambiguous boundaries.
- Representative evidence is selected from segments, not from loose frames.

### 3. Chronology-First SOP Cleanup

- Added [pipeline/sop_cleanup.py](<G:/My Drive/Video-to-SOP/pipeline/sop_cleanup.py>).
- Cleanup now removes obvious non-operational noise, removes weak passive review steps, merges only conservative same-intent duplicates, preserves evidence fields, validates chronology, repairs ordering when needed, and assigns phase labels without reordering the workflow.
- Phase sections can repeat later in the SOP. Steps are never moved into earlier buckets just to make the document look tidier.

### 4. Stronger Quality Gate

- The app now scores the cleaned SOP and assigns readiness:
  - `demo_ready`
  - `needs_review`
  - `not_ready`
- Quality scoring considers low-confidence volume, noise, duplicate candidates, passive filler, and chronology violations.

## Current Pipeline

The application currently supports:

- video upload and local storage
- dense frame extraction
- adaptive screen-state segmentation
- OCR preprocessing and extraction
- rule-based system classification
- bounded OpenAI step generation
- risky-step verification
- deterministic SOP cleanup and quality scoring
- DOCX export

The main last-mile quality guard is now the deterministic cleanup layer in [pipeline/sop_cleanup.py](<G:/My Drive/Video-to-SOP/pipeline/sop_cleanup.py>), not the prompt alone.

## Requirements

- Python 3.11 or newer
- `streamlit`
- `opencv-python`
- `numpy`
- `pillow`
- `python-docx`
- `openai`
- `pytesseract`
- `python-dotenv`
- Native Tesseract OCR installed on the system. On Windows, the app also checks `C:\Program Files\Tesseract-OCR\tesseract.exe`.

Python package dependencies are listed in [requirements.txt](<G:/My Drive/Video-to-SOP/requirements.txt>).

## Setup

Install Python dependencies:

```powershell
python -m pip install -r requirements.txt
```

For OCR, install native Tesseract separately. The repository includes the Python bridge (`pytesseract`) but does not vendor the native OCR binary itself.

```powershell
winget install UB-Mannheim.TesseractOCR
```

If Tesseract is installed but not on PATH, set:

```powershell
$env:TESSERACT_CMD="C:\Program Files\Tesseract-OCR\tesseract.exe"
```

Check local prerequisites:

```powershell
python scripts\check_prereqs.py
```

For a full first-run walkthrough, see [docs/quickstart.md](<G:/My Drive/Video-to-SOP/docs/quickstart.md>).

## OpenAI Configuration

Recommended local `.env` setup:

```powershell
Copy-Item .env.example .env
notepad .env
```

Set:

```text
OPENAI_API_KEY=your_api_key
OPENAI_MODEL=gpt-5.5
TESSERACT_CMD=C:\Program Files\Tesseract-OCR\tesseract.exe
```

The app automatically loads `.env` from the repo root. You can also set real environment variables before launch:

```powershell
$env:OPENAI_API_KEY="your_api_key"
$env:OPENAI_MODEL="gpt-5.5"
```

Optional Streamlit secrets are also supported through `.streamlit/secrets.toml`:

```toml
OPENAI_API_KEY = "your_api_key"
OPENAI_MODEL = "gpt-5.5"
```

Configuration precedence is:

```text
real environment variable > .env > Streamlit secrets > default
```

If `OPENAI_API_KEY` is not set, the app uses OCR draft mode when OCR text exists. If neither OpenAI nor OCR text is available, the app blocks production SOP generation and only allows an explicit diagnostic draft.

Current default cost estimates use GPT-5.5 pricing defaults of `$5 / 1M input tokens` and `$30 / 1M output tokens`, based on [OpenAI API Pricing](https://openai.com/api/pricing/) as checked on April 25, 2026.

## Public GitHub Safety

This repository is intended to be safe for public GitHub use if secrets and generated artifacts stay out of Git.

Current safety measures:

- [.gitignore](<G:/My Drive/Video-to-SOP/.gitignore>) ignores `.env`, `.env.*`, `.streamlit/secrets.toml`, `jobs/`, SQLite databases, logs, caches, and local virtual environments.
- [.env.example](<G:/My Drive/Video-to-SOP/.env.example>) contains placeholders only.
- No API keys should ever be committed.

Never commit:

- real OpenAI API keys
- `.streamlit/secrets.toml`
- uploaded videos
- screenshots
- OCR artifacts
- generated SOPs
- SQLite job databases
- local logs

If a real key is ever committed or pushed, revoke it immediately and create a new one.

## Running The App

Launch Streamlit:

```powershell
python -m streamlit run app.py
```

Default local URL:

```text
http://localhost:8501
```

## UI Workflow

1. Enter a process name.
2. Optionally enter department or system notes.
3. Optionally change the target audience.
4. Choose a quality profile.
5. Upload a recording.
6. Start the job.
7. Wait for the worker to finish.
8. Review cleanup diagnostics and readiness.
9. Download the DOCX.

After completion, the app shows:

- final step count
- original step count
- cleaned step count
- removed count
- merged count
- quality score
- readiness label
- chronology status
- segmentation diagnostics such as screen states and boundary candidates

## Quality Profiles

Profiles are defined in [pipeline/config.py](<G:/My Drive/Video-to-SOP/pipeline/config.py>).

### `Balanced`

Default profile for general use:

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

### `Lowest cost`

Fastest and cheapest profile:

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

### `Highest accuracy`

More local evidence and more bounded review:

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

The app shows a rough maximum API estimate before a job starts.

## Job Output And Artifacts

Each job is stored under:

```text
jobs/{job_id}/
```

Important files:

- `input.mp4`
- `sop.docx`
- `frames/`
- `ocr/`
- `artifacts/frames.json`
- `artifacts/frame_metrics.json`
- `artifacts/boundary_candidates.json`
- `artifacts/screen_states.json`
- `artifacts/event_segments.json`
- `artifacts/segmentation_report.md`
- `artifacts/ocr_raw.json`
- `artifacts/events.json`
- `artifacts/steps_generated.json`
- `artifacts/steps_validated.json`
- `artifacts/sop_cleanup.json`
- `artifacts/steps_final.json`

What the key artifacts mean:

- `frames.json`: dense metric-frame extraction output
- `frame_metrics.json`: per-frame local boundary metrics
- `boundary_candidates.json`: adaptive threshold decisions
- `screen_states.json`: recurring state signatures and state counts
- `event_segments.json`: segment evidence used for SOP generation
- `segmentation_report.md`: human-readable segmentation summary
- `ocr_raw.json`: OCR output captured from selected evidence frames
- `steps_generated.json`: initial model or fallback step wording
- `steps_validated.json`: post-verification, pre-cleanup steps
- `sop_cleanup.json`: removed steps, merged steps, phase summary, chronology results, and quality report
- `steps_final.json`: cleaned steps used in the DOCX

## Documentation Map

- [docs/architecture.md](<G:/My Drive/Video-to-SOP/docs/architecture.md>)
- [docs/pipeline.md](<G:/My Drive/Video-to-SOP/docs/pipeline.md>)
- [docs/configuration.md](<G:/My Drive/Video-to-SOP/docs/configuration.md>)
- [docs/development.md](<G:/My Drive/Video-to-SOP/docs/development.md>)
- [docs/troubleshooting.md](<G:/My Drive/Video-to-SOP/docs/troubleshooting.md>)

## Verification Commands

Compile:

```powershell
python -m compileall app.py worker.py pipeline storage tests scripts
```

Run tests:

```powershell
python -m unittest discover -s tests
```

Run no-API smoke test:

```powershell
python scripts/smoke_test.py
```

## Current Test Coverage

The test suite currently covers:

- OCR cleaning
- system classification
- event clustering basics
- generation fallback behavior
- risk verification fallback behavior
- adaptive segmentation thresholds and scroll collapse
- recurring screen-state handling
- synthetic SAP-to-Excel-to-SAP segmentation
- deterministic SOP cleanup
- chronology validation and repair
- repeated phase sections in timeline order
- generic non-Excel browser workflow cleanup

## Known Limits

- SOP quality still depends on source recording quality.
- Very fast actions between sampled frames may still be missed.
- OCR quality depends heavily on text size, contrast, and Tesseract availability.
- Browser-based internal tools can still be hard to classify precisely without stronger visible labels.
- The smoke test proves pipeline continuity, not product-quality SOP output.
- The app is local and single-user; it is not a hosted multi-user service.
