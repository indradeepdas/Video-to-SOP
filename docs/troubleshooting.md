# Troubleshooting

This document reflects the current architecture: adaptive segmentation, optional native Tesseract OCR, bounded OpenAI generation and review, chronology-first cleanup, and final readiness scoring.

## Streamlit Will Not Start

Run:

```powershell
python -m streamlit run app.py
```

If `streamlit` is missing:

```powershell
python -m pip install -r requirements.txt
```

If port `8501` is busy:

```powershell
python -m streamlit run app.py --server.port 8502
```

## Upload Fails

Check:

[.streamlit/config.toml](<G:/My Drive/Video-to-SOP/.streamlit/config.toml>)

The current upload limit is 2048 MB.

Try:

- converting the recording to MP4
- reducing extreme resolution
- avoiding unusual codecs

## Video Cannot Be Opened

If the worker fails during frame extraction, OpenCV likely cannot decode the file.

Try:

- converting to MP4
- using a common H.264 export
- reducing resolution
- confirming the file is not corrupted

## OCR Is Empty

Native Tesseract is probably missing or not on PATH.

Check:

```powershell
tesseract --version
```

If the command fails:

- install native Tesseract
- restart the terminal
- restart Streamlit

Important distinction:

- `pytesseract` is already in Python dependencies
- the native Tesseract executable is still a separate system install

The app still runs without native Tesseract, but OCR-derived evidence and final SOP quality will usually be lower.

## OpenAI Calls Fail

Check:

```powershell
$env:OPENAI_API_KEY
$env:OPENAI_MODEL
```

Also run:

```powershell
python scripts\check_prereqs.py
```

Common causes:

- missing API key
- invalid model name
- rate limit
- network issue
- account or billing problem

If OpenAI fails, the pipeline falls back locally where possible.

## `.env` Exists But OpenAI Is Not Detected

The app now auto-loads `.env` from the repo root. If OpenAI is still missing:

- confirm the file is named exactly `.env`
- confirm it is in the repo root, next to `app.py`
- confirm the key is not left as `replace_me`
- restart Streamlit after editing `.env`
- check whether `VIDEO2SOP_DISABLE_OPENAI=1` is set

Run:

```powershell
python scripts\check_prereqs.py
```

The output should show `.env found`, `OpenAI configured`, and `OpenAI key source`.

## Tesseract Installed But Not Detected

If OCR is unavailable after installing Tesseract:

- restart PowerShell and Streamlit
- confirm the binary exists at `C:\Program Files\Tesseract-OCR\tesseract.exe`
- add `TESSERACT_CMD=C:\Program Files\Tesseract-OCR\tesseract.exe` to `.env`

Run:

```powershell
python scripts\check_prereqs.py
```

The check prints the resolved command, version, and OCR smoke text.

## App Is Stuck In Diagnostic Mode

Diagnostic mode means the app has neither OpenAI vision nor usable OCR text.

Fix in this order:

1. configure `OPENAI_API_KEY`
2. install Tesseract
3. run `python scripts\check_prereqs.py`
4. restart Streamlit

Diagnostic drafts are intentionally blocked from `demo_ready`.

## SOP Looks Too Generic

Likely causes:

- weak or missing OCR
- no OpenAI key
- low-resolution recording
- extremely fast workflow actions
- low-evidence segmentation

Try:

- confirming the sidebar says `Mode: production vision`
- installing native Tesseract
- setting `OPENAI_API_KEY` in `.env`
- using `Balanced` or `Highest accuracy`
- recording at higher resolution
- leaving each meaningful screen visible slightly longer

If many rows say “Review the process state shown,” the run likely used diagnostic fallback or had too little semantic evidence.

## Too Many Duplicate Or Weak Review Steps

Check:

```text
jobs/{job_id}/artifacts/steps_generated.json
jobs/{job_id}/artifacts/steps_validated.json
jobs/{job_id}/artifacts/sop_cleanup.json
```

This tells you where the issue started:

- generation produced filler
- validation did not remove enough weak steps
- cleanup was conservative because too many steps were borderline

## Cleanup Removed Too Much

Check:

```text
jobs/{job_id}/artifacts/sop_cleanup.json
```

Relevant fields:

- `removed_steps`
- `merged_steps`
- `quality_report.warnings`

If cleanup thinks more than 40 percent of steps are borderline removable, it becomes conservative and records this warning:

```text
Cleanup was conservative because too many steps were at risk of removal.
```

If the final SOP is still weak after that, the problem is usually upstream evidence quality.

## Quality Report Says `not_ready`

This is expected when:

- weak fallback steps dominate
- cleanup removes nearly all meaningful output
- chronology was badly broken and the remaining SOP is still weak
- too many low-confidence steps remain
- too few evidence-backed steps survive

Check:

```text
jobs/{job_id}/artifacts/sop_cleanup.json
```

Important fields:

- `quality_score`
- `readiness`
- `chronological_order_valid`
- `chronological_violations_count`
- `warnings`

## Chronology Problems

Cleanup now validates chronology and repairs ordering automatically when metadata shows that steps are out of order.

Ordering precedence is:

1. `start_time_seconds`
2. `source_event_index`
3. `original_step_number`

If chronology was repaired, the cleanup report records that fact in warnings. Chronology issues also reduce the quality score.

Check:

```text
jobs/{job_id}/artifacts/sop_cleanup.json
```

Fields:

- `quality_report.chronological_order_valid`
- `quality_report.chronological_violations_count`
- `quality_report.warnings`

## Phases Look Repeated

Repeated phases are now valid by design.

The DOCX no longer groups all steps globally by phase label. Instead:

- each step gets a phase label
- steps stay chronological
- a phase heading appears when the phase label changes in the timeline
- the same phase can appear again later if the workflow returns to that type of work

If phases repeat, that is usually the correct behavior rather than a bug.

## SOP Mentions The Wrong System

Classification is still rule-based. Ambiguous internal web apps can still be labeled `Browser` or `Other`.

Relevant module:

[pipeline/classify.py](<G:/My Drive/Video-to-SOP/pipeline/classify.py>)

Improve by adding stronger system terms and updating tests.

## Slow Runtime

Runtime depends on:

- video length
- codec
- resolution
- OCR availability
- CPU speed
- OpenAI latency
- selected profile

For faster runs, use `Lowest cost`.

For stronger segmentation and review quality, use `Balanced` or `Highest accuracy`.

## Inspecting A Job

Open:

```text
jobs/{job_id}/artifacts/
```

Current useful files:

- `frames.json`
- `frame_metrics.json`
- `boundary_candidates.json`
- `screen_states.json`
- `event_segments.json`
- `segmentation_report.md`
- `ocr_raw.json`
- `steps_generated.json`
- `steps_validated.json`
- `sop_cleanup.json`
- `steps_final.json`

These files tell you:

- how dense frame extraction behaved
- how segmentation decided boundaries
- how many screen states were found
- what OCR captured
- what generation produced
- what cleanup removed or merged
- why the final SOP was or was not considered ready
