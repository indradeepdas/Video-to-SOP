# Quickstart

This is the shortest path to one successful Video2SOP run on Windows.

## 1. Install Python Dependencies

```powershell
cd "G:\My Drive\Video-to-SOP"
python -m pip install -r requirements.txt
```

## 2. Install Native Tesseract

```powershell
winget install UB-Mannheim.TesseractOCR
```

If Windows does not put it on PATH, keep this value in `.env`:

```text
TESSERACT_CMD=C:\Program Files\Tesseract-OCR\tesseract.exe
```

## 3. Configure OpenAI

```powershell
Copy-Item .env.example .env
notepad .env
```

Set:

```text
OPENAI_API_KEY=your_api_key
OPENAI_MODEL=gpt-5.5
```

Do not commit `.env`. It is ignored by Git.

## 4. Check Prerequisites

```powershell
python scripts\check_prereqs.py
```

Expected production-ready signals:

- `.env found: True`
- `OpenAI configured: True`
- `Generation mode: production_vision`
- `Tesseract available: True`
- OCR smoke text contains readable words

## 5. Run The Local Demo

This runs a bundled synthetic workflow without paid OpenAI calls by default:

```powershell
python scripts\demo_run.py
```

To test the production vision path with your OpenAI key:

```powershell
python scripts\demo_run.py --use-openai
```

## 6. Run The App

```powershell
python -m streamlit run app.py
```

Open the local URL shown by Streamlit, upload a screen recording, and confirm the sidebar says:

- `OpenAI: configured from .env` or `configured from environment`
- `OCR: available`
- `Mode: production vision`

If the app says `OCR draft` or `diagnostic only`, the output is not a production-grade SOP.

## 7. Optional Benchmark Run

Use this when validating a showcase video from the command line:

```powershell
python scripts\benchmark_job.py "C:\path\to\workflow-video.mp4" --profile "Showcase fast"
```

The report prints runtime, stage timings, event count, cleaned step count, workflow density, phase errors, long single-step segments, readiness, and blockers.
