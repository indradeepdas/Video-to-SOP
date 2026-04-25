# Troubleshooting

## Streamlit Will Not Start

Run:

```powershell
python -m streamlit run app.py
```

If `streamlit` is not found, reinstall dependencies:

```powershell
python -m pip install -r requirements.txt
```

If port 8501 is busy, Streamlit will usually choose another port or you can specify one:

```powershell
python -m streamlit run app.py --server.port 8502
```

## Upload Fails

Check `.streamlit/config.toml`.

The configured upload limit is 2048 MB. Very large videos may still be slow to upload or process.

Try exporting the recording as MP4 with a common codec.

## Video Cannot Be Opened

OpenCV must be able to decode the video. If a job fails during frame extraction:

- convert the file to MP4
- reduce resolution if extremely large
- avoid exotic codecs
- confirm the file is not corrupted

## OCR Is Empty

Tesseract may be missing or not on PATH.

Check from PowerShell:

```powershell
tesseract --version
```

If this fails, install Tesseract and restart the terminal before launching Streamlit.

Video2SOP still runs without Tesseract, but confidence may be lower.

## OpenAI Calls Fail

Confirm:

```powershell
$env:OPENAI_API_KEY
$env:OPENAI_MODEL
```

Common causes:

- missing API key
- invalid model name
- network issue
- rate limit
- billing or account limitation

If OpenAI fails, the app falls back to local step generation where possible.

## DOCX Has Too Few Steps

This is intentional when evidence is limited. The app does not invent extra steps to reach a target count.

Improve the source recording:

- slow down during important actions
- keep screens visible for several seconds
- avoid rapid tab switching
- zoom in enough for text to be readable
- record from process start to process finish

## DOCX Steps Are Too Generic

Likely causes:

- OCR was unavailable or weak
- recording resolution was too low
- the app was running without `OPENAI_API_KEY`
- the selected profile was `Lowest cost`

Try:

- installing Tesseract
- using `Balanced` or `Highest accuracy`
- setting `OPENAI_API_KEY`
- recording at higher resolution

## SOP Mentions Wrong System

Validation corrects common system mismatches, but ambiguous browser-based apps can still be classified as Browser or Other.

Add system terms to `pipeline/classify.py` and a test in `tests/test_pipeline.py`.

## Slow Runtime

Runtime depends on:

- video length
- codec
- resolution
- OCR availability
- CPU speed
- OpenAI latency

Use `Lowest cost` for faster experimental runs.

## Inspecting a Job

Open:

```text
jobs/{job_id}/artifacts/
```

Useful files:

- `selected_frames.json`
- `ocr_raw.json`
- `classified.json`
- `events.json`
- `steps_final.json`

These show where evidence was kept, dropped, or generalized.
