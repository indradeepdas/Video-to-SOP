# Showcase Checklist

Use this before publishing a LinkedIn demo or asking others to try the repo.

## Prerequisites

Run:

```powershell
python scripts\check_prereqs.py
```

Required signals for a production showcase:

- `.env found: True` or OpenAI configured from real environment variables
- `OpenAI configured: True`
- `Generation mode: production_vision`
- `Tesseract available: True`
- OCR smoke text is readable

## Local Demo

Run the no-cost local demo:

```powershell
python scripts\demo_run.py
```

Then run the production vision demo when you are comfortable using your OpenAI key:

```powershell
python scripts\demo_run.py --use-openai
```

The output should produce a DOCX path, step count, generation mode, readiness, and any blockers.

## Benchmark A Real Video

For a 7-9 minute showcase recording, run:

```powershell
python scripts\benchmark_job.py "C:\path\to\workflow-video.mp4" --profile "Showcase fast"
```

Check:

- total runtime is close to the five-minute target on the showcase machine
- event segments are not over-compressed
- step density is credible for the video length
- phase errors are zero
- long single-step segments are zero or have clear blockers
- readiness is `demo_ready` only when blockers are empty

## App Demo

Run:

```powershell
python -m streamlit run app.py
```

Before upload, confirm the sidebar shows:

- OpenAI configured
- OCR available
- production vision mode

After generation, confirm:

- no diagnostic fallback
- readiness blockers are empty or clearly explain manual review
- DOCX title is human-readable
- screenshots appear under steps
- final readiness matches human judgment

Do not present an OCR draft or diagnostic draft as a production-quality SOP.
