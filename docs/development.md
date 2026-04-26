# Development Guide

This guide reflects the current code after the recent upgrades for public-repo safety, adaptive segmentation, chronology-first cleanup, and SOP quality scoring.

## Local Setup

Install dependencies:

```powershell
python -m pip install -r requirements.txt
```

Start the app:

```powershell
python -m streamlit run app.py
```

## Required Verification Commands

These commands are the current baseline after any meaningful change:

```powershell
python -m compileall app.py worker.py pipeline storage tests scripts
python -m unittest discover -s tests
python scripts/smoke_test.py
```

## Current Product Priorities

The current MVP-quality focus is:

1. Better screen-state segmentation.
2. Better conservative step wording.
3. Better deterministic cleanup and readiness scoring.
4. Better docs and safer public-repo hygiene.

The main last-mile quality gate now lives in [pipeline/sop_cleanup.py](<G:/My Drive/Video-to-SOP/pipeline/sop_cleanup.py>), not in the prompt alone.

## Development Principles

- Keep the architecture local-first.
- Use GPT only after local evidence has been narrowed down.
- Keep explicit caps on frames, OCR, events, steps, and model calls.
- Preserve chronology above organizational tidiness.
- Cleanup may remove or merge steps, but it must not reorder the actual workflow.
- Prefer conservative cleanup over aggressive rewriting.
- Never invent missing operational steps.
- Never pad a weak SOP to make it look complete.
- Keep the app usable without OpenAI.

## Working In Specific Areas

### Segmentation

Module:

[pipeline/segmentation.py](<G:/My Drive/Video-to-SOP/pipeline/segmentation.py>)

Guidelines:

- preserve adaptive thresholding
- keep dense frame scoring local
- treat recurring states carefully
- treat scroll collapse conservatively
- keep GPT boundary review sparse and bounded

### OCR

Modules:

- [pipeline/ocr.py](<G:/My Drive/Video-to-SOP/pipeline/ocr.py>)
- [pipeline/clean_ocr.py](<G:/My Drive/Video-to-SOP/pipeline/clean_ocr.py>)

Guidelines:

- remember that `pytesseract` is only the Python bridge
- do not assume native Tesseract exists
- keep fallback behavior non-fatal
- preserve business terms when cleaning OCR noise

### System Classification

Module:

[pipeline/classify.py](<G:/My Drive/Video-to-SOP/pipeline/classify.py>)

Guidelines:

- keep classification deterministic
- add rules carefully
- update tests when changing heuristics

### SOP Cleanup

Module:

[pipeline/sop_cleanup.py](<G:/My Drive/Video-to-SOP/pipeline/sop_cleanup.py>)

Guidelines:

- chronology is the top invariant
- do not move later steps into earlier phase groups
- repeated phase sections are valid
- remove only obvious non-operational noise or weak passive filler
- preserve validation checkpoints
- preserve screenshot links and timing metadata
- keep merge logic time- and context-aware

### DOCX Export

Module:

[pipeline/docx_export.py](<G:/My Drive/Video-to-SOP/pipeline/docx_export.py>)

Guidelines:

- render cleaned steps only
- render phase sections in timeline order
- allow repeated phase headings
- keep the cleanup appendix in sync with the cleanup report schema
- keep screenshot evidence lines aligned with actual step metadata

### Worker Orchestration

Module:

[worker.py](<G:/My Drive/Video-to-SOP/worker.py>)

Guidelines:

- write artifacts as the pipeline progresses
- update job progress and messages with meaningful stages
- keep fallback generation working
- keep `meta_json` aligned with what the UI and DOCX expect

## Prompt Editing

Prompt-bearing modules:

- [pipeline/generate.py](<G:/My Drive/Video-to-SOP/pipeline/generate.py>)
- [pipeline/verify.py](<G:/My Drive/Video-to-SOP/pipeline/verify.py>)

Prompt changes should preserve:

- JSON-only output
- visible-evidence-only behavior
- conservative generic wording under uncertainty
- no hallucinated clicks, values, fields, or outcomes

Do not move cleanup responsibilities into prompts if they can be handled deterministically afterward.

## Current Tests

[tests/test_pipeline.py](<G:/My Drive/Video-to-SOP/tests/test_pipeline.py>) covers:

- OCR cleaning
- system classification
- event clustering basics
- risk marking and no-API sanitization
- validation and fallback phase grouping
- model JSON parsing and fallback generation

[tests/test_segmentation.py](<G:/My Drive/Video-to-SOP/tests/test_segmentation.py>) covers:

- adaptive threshold selection
- OCR token Jaccard behavior
- scroll collapse
- recurring screen-state handling
- synthetic SAP-to-Excel-to-SAP segmentation

[tests/test_sop_cleanup.py](<G:/My Drive/Video-to-SOP/tests/test_sop_cleanup.py>) covers:

- presenter, outro, and social-noise removal
- generic visible-screen filler removal
- validation checkpoint preservation
- conservative duplicate merging
- no merge for distinct meaningful actions
- PivotTable phase inference
- repeated phase sections in timeline order
- chronology validation and repair
- generic non-Excel browser workflow cleanup
- screenshot evidence preservation
- readiness scoring

## Smoke Test

[scripts/smoke_test.py](<G:/My Drive/Video-to-SOP/scripts/smoke_test.py>) creates a synthetic local video, removes `OPENAI_API_KEY`, runs the worker, and asserts that a DOCX is produced.

This proves:

- local-first fallback still works
- worker orchestration still completes
- cleanup and quality report still serialize
- DOCX export still runs

It does not prove that the output is product-quality for a real workflow video.

## Debugging A Real Job

When debugging a real run, inspect:

```text
jobs/{job_id}/artifacts/
```

Most useful files:

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

The normal failure chain to check is:

1. Did segmentation split the workflow sensibly?
2. Did OCR capture enough useful business text?
3. Did generation overproduce passive or duplicate steps?
4. Did cleanup remove only weak noise and filler?
5. Did the final readiness state match the actual quality?

## Public GitHub Safety

The repository is configured for safe public publishing if local artifacts remain ignored.

Relevant files:

- [.gitignore](<G:/My Drive/Video-to-SOP/.gitignore>)
- [.env.example](<G:/My Drive/Video-to-SOP/.env.example>)

Never stage:

- `jobs/`
- SQLite DBs
- `.env`
- Streamlit secrets
- generated SOPs
- local logs

## Known Limits

- The app is still local and single-user.
- Jobs run in background threads, not through a robust external queue.
- SQLite stores lightweight metadata only.
- Streamlit reruns the script while worker threads are active.
- The app remains an MVP-quality local tool, not a hosted platform.
