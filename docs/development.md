# Development Guide

## Local Setup

```powershell
python -m pip install -r requirements.txt
```

Run the app:

```powershell
python -m streamlit run app.py
```

Run checks:

```powershell
python -m compileall app.py worker.py pipeline storage tests scripts
python -m unittest discover -s tests
python scripts/smoke_test.py
```

## Development Principles

- Keep local evidence processing first.
- Use GPT only after local pruning.
- Keep hard caps on frames, OCR, steps, and model calls.
- Prefer conservative wording over hallucinated precision.
- Always produce a DOCX when enough evidence exists.
- Do not pad SOPs with invented steps.

## Adding System Rules

System rules live in `pipeline/classify.py`.

Add terms to the relevant list, then add or update tests in `tests/test_pipeline.py`.

Classification should stay fast and deterministic. Avoid adding model calls for basic system detection.

## Adding Action Hints

Action hints live in `pipeline/cluster.py`.

Hints influence event scoring and fallback step language. Keep hints broad:

- filter
- export
- data entry
- review
- post/save
- navigation

Avoid UI-specific hints like exact button names unless they are broadly useful.

## Editing Prompts

Generation prompt:

```text
pipeline/generate.py
```

Verification prompt:

```text
pipeline/verify.py
```

Prompt changes should preserve:

- JSON-only output.
- visible-evidence-only rule.
- no hallucinated clicks, values, or outcomes.
- conservative generic action wording when uncertain.

## Smoke Test

`scripts/smoke_test.py` creates a synthetic video with SAP and Excel-like screens, runs the worker with `OPENAI_API_KEY` removed, and asserts that a DOCX exists.

This test proves the local fallback path works.

## Unit Tests

`tests/test_pipeline.py` covers:

- OCR cleaning.
- system classification.
- duplicate event filtering.
- risk marking and no-API sanitization.
- validation and phase grouping.
- model JSON parsing and fallback generation.

`tests/test_segmentation.py` covers:

- adaptive segmentation thresholds.
- OCR token Jaccard behavior.
- scroll-only collapse.
- screen-state recurrence.
- synthetic SAP-to-Excel-to-SAP segmentation.

`tests/test_sop_cleanup.py` covers:

- presenter/outro/social noise removal.
- passive review cleanup.
- validation checkpoint preservation.
- adjacent duplicate merging.
- PivotTable phase assignment.
- quality scoring and demo-readiness.
- screenshot evidence preservation.
- chronological order validation and repair.
- repeated phase sections in timeline order.
- generic non-Excel browser workflow cleanup.

## Known Development Limits

- There is no multi-user queue.
- Jobs run in local background threads.
- Streamlit reruns the app script while job threads run.
- SQLite stores job metadata but not large artifacts.
- The app is intended for local hobbyist use, not hosted production.
