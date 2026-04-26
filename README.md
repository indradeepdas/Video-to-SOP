# Video2SOP Fast Mode

Video2SOP is a local Streamlit application that turns a screen recording into a screenshot-backed SOP DOCX. It is designed for business process recordings, not general video analysis.

The app samples frames, detects adaptive screen-state boundaries, runs OCR when available, classifies systems such as SAP and Excel, asks OpenAI for conservative SOP wording when configured, verifies risky steps, and exports a Word document with screenshots and confidence indicators.

## What It Produces

The generated DOCX includes:

- SOP title based on the process name.
- Summary, prerequisites, and assumptions.
- Phase-grouped steps.
- Chronological phase sections that preserve process order.
- Screenshot evidence for each step.
- System, action, expected output, and confidence for each step.
- Low-confidence review checklist.
- Cleanup and quality report.
- Job metadata appendix.

The app does not pad the SOP with invented steps. If a short or repetitive recording only supports fewer than 25 steps, it produces fewer steps and adds a warning.

## Requirements

- Python 3.11 or newer.
- Streamlit.
- OpenCV.
- python-docx.
- Optional but recommended: Tesseract OCR installed on your system.
- Optional: `OPENAI_API_KEY` for GPT-5.5 generation and verification.

Python dependencies are listed in `requirements.txt`.

## Setup

```powershell
python -m pip install -r requirements.txt
```

For best OCR, install Tesseract separately and make sure `tesseract.exe` is on your PATH. If Tesseract is missing, Video2SOP still runs and relies on visual evidence, local rules, and model vision when configured.

## Public GitHub Safety

This project is safe to publish only if secrets and generated job data stay out of Git.

- Never commit a real OpenAI API key.
- Keep real keys in environment variables or a local `.env` file.
- Use `.env.example` as the public template.
- Keep `.streamlit/secrets.toml` local only.
- Do not commit `jobs/`, `storage/*.sqlite3`, logs, uploaded videos, screenshots, OCR artifacts, or generated SOP DOCX files.
- If a real key is ever committed or pushed, revoke it immediately and create a new key.

## OpenAI Configuration

Set your API key before launching the app:

```powershell
$env:OPENAI_API_KEY="your_api_key"
$env:OPENAI_MODEL="gpt-5.5"
```

Or create a local `.env` file from `.env.example` for your own notes. The app reads environment variables directly; if you use `.env`, load it in your shell or with your preferred local tooling before starting Streamlit. `.env` is ignored by Git.

If `OPENAI_API_KEY` is not set, the app runs in fallback mode and still produces a DOCX using local evidence.

Current default pricing estimates use GPT-5.5 at `$5 / 1M input tokens` and `$30 / 1M output tokens`, based on OpenAI's API pricing page as checked on April 25, 2026: https://openai.com/api/pricing/

## Run

```powershell
python -m streamlit run app.py
```

Then open the local Streamlit URL shown in the terminal, usually:

```text
http://localhost:8501
```

## Basic Workflow

1. Enter a process name, department/system notes, and target audience.
2. Keep the default `Balanced` quality profile unless you need lower cost or higher accuracy.
3. Upload a screen recording file.
4. Click `Generate SOP`.
5. Wait for processing to finish.
6. Download the DOCX.

## Quality Profiles

- `Balanced`: default. 1-second local metric pass, max 60 OCR frames, 40 final steps, and 6 GPT calls.
- `Lowest cost`: fewer frames, fewer events, and fewer verification rows.
- `Highest accuracy`: more local evidence and more GPT context, still capped to avoid uncontrolled spend.

The sidebar and upload form show a rough maximum API estimate before the job starts.

## Job Output

Each job is stored locally under:

```text
jobs/{job_id}/
```

Important files:

- `input.mp4`: uploaded recording.
- `frames/`: sampled screenshots.
- `ocr/`: preprocessed OCR images when Tesseract is available.
- `artifacts/*.json`: pipeline evidence and intermediate outputs.
- `artifacts/segmentation_report.md`: adaptive boundary and screen-state diagnostics.
- `artifacts/sop_cleanup.json`: removed steps, merged steps, phase summary, quality score, and readiness.
- `sop.docx`: final SOP.

## Documentation

More detailed documentation:

- `docs/architecture.md`
- `docs/pipeline.md`
- `docs/configuration.md`
- `docs/development.md`
- `docs/troubleshooting.md`

## Tests

Run static compilation:

```powershell
python -m compileall app.py worker.py pipeline storage tests scripts
```

Run unit tests:

```powershell
python -m unittest discover -s tests
```

Run a no-API smoke test:

```powershell
python scripts/smoke_test.py
```

## Known Limits

- SOP quality depends on screen recording quality.
- Very fast clicks between sampled frames may be missed.
- OCR depends on font size, resolution, contrast, and Tesseract availability.
- The model is instructed not to hallucinate, but low-confidence steps should still be reviewed.
- A 45-minute recording should be practical, but runtime depends on machine speed, video codec, OCR availability, and API latency.
