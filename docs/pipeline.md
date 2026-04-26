# Pipeline Details

The current pipeline is designed for business-process SOP generation. It does not attempt to label every frame in the recording. Instead, it identifies meaningful screen transitions, extracts bounded evidence, generates conservative steps, and then applies deterministic cleanup and quality control before export.

## 1. Upload And Job Creation

The user uploads a recording in Streamlit. The file is written to:

```text
jobs/{job_id}/input.mp4
```

The initial job record also stores:

- `process_name`
- `department_notes`
- `target_audience`
- selected `quality_profile`
- rough `cost_estimate`

## 2. Dense Frame Extraction

The worker performs a dense local pass over the video using the selected profile's metric interval.

Balanced profile values:

- `metric_interval_seconds = 1.0`
- `max_metric_frames = 2800`

Each extracted frame record can include:

- `frame_id`
- `time_sec`
- `path`
- `width`
- `height`
- `diff_score`
- `image_hash`

Frames are resized to a maximum width of 1280 pixels.

Artifact:

- `frames.json`

## 3. Adaptive Boundary Detection

The segmentation engine computes a boundary score between adjacent dense frames. The current score is based on multiple local signals:

- pixel absolute difference
- SSIM structural change
- edge-map delta
- perceptual hash distance

Thresholding is adaptive per job. The logic uses:

- median boundary score
- median absolute deviation (MAD)
- percentile fallback
- hysteresis so one noisy frame does not produce a burst of false boundaries

Artifacts:

- `frame_metrics.json`
- `boundary_candidates.json`

## 4. Screen-State Segmentation

Boundary candidates are converted into event segments. This is now the main evidence unit for SOP generation.

Segments can carry:

- `start_time_sec`
- `end_time_sec`
- `before_frame`
- `entry_frame`
- `stable_frame`
- `after_frame`
- `boundary_score`
- `screen_state_id`
- `confidence_components`

Artifacts:

- `screen_states.json`
- `event_segments.json`
- `segmentation_report.md`

## 5. OCR

OCR is bounded by the selected profile and runs only on chosen evidence frames, not on every dense metric frame.

Balanced profile:

- `max_ocr_frames = 60`

When native Tesseract is available:

- preprocessed OCR images are written to `jobs/{job_id}/ocr`
- OCR runs with multiple fast page segmentation strategies
- the stronger text result is retained

When native Tesseract is not available:

- OCR text remains empty
- the pipeline continues
- later confidence is usually lower because OCR-supported evidence is missing

Artifact:

- `ocr_raw.json`

## 6. OCR Cleaning

OCR cleaning removes UI noise such as:

- menus
- toolbar labels
- timestamps
- decorative separators
- repeated short UI fragments

It tries to preserve business-relevant terms such as:

- invoice
- supplier
- payment
- posting
- export
- reconciliation
- amount
- status

## 7. System Classification

System classification is deterministic and rule-based.

Supported classes:

- SAP
- Excel
- Email
- Slack/Teams
- Browser
- PDF
- File Explorer
- Other

Classification is used by:

- segmentation enrichment
- later generation prompts
- cleanup phase inference
- final document labeling

## 8. Segment Enrichment

Each segment is enriched with:

- cleaned OCR text
- rule-based system class
- OCR delta relative to nearby segments
- local action hint
- confidence components

Local action hints are broad and deterministic. They cover categories such as:

- navigation
- filter
- export
- data entry
- review
- post or save

## 9. Scroll Collapse And Segment Pruning

The segmentation pipeline removes low-value fragmentation:

- scroll-only segments can be collapsed
- repeated same-state low-evidence fragments can be merged locally
- recurring states later in the workflow are still preserved as revisits when they matter

This stage is local and deterministic. It does not use GPT by default.

## 10. Optional Ambiguous Boundary Review

Balanced and Highest accuracy profiles can send a capped set of uncertain neighboring segments to GPT vision. GPT only answers whether the local boundary should stay or collapse.

This is intentionally narrow:

- it is not the main segmentation engine
- it is capped by profile
- it only applies after local pruning

## 11. SOP Step Generation

Event segments are sent to GPT in compact batches.

Balanced profile uses:

- `batch_size = 9`
- `max_gpt_calls = 6`

The generation prompt is constrained to:

- treat one event as one possible SOP step
- use stable evidence first
- avoid hallucinated clicks, field values, and unsupported outcomes
- choose generic wording when uncertain
- return JSON only

If OpenAI is unavailable or returns invalid output, the pipeline falls back to local deterministic step wording.

Artifact:

- `steps_generated.json`

## 12. Risk Verification

Risk detection marks steps when:

- confidence is not high
- wording contains exact values
- wording is too specific for the visible evidence
- the model system and local rule-based system disagree

Only a capped number of risky rows are verified so API spend stays bounded.

Artifact:

- risk-reviewed output is persisted through `steps_validated.json`

## 13. Validation

Before cleanup, validation enforces:

- no duplicate normalized steps
- no obvious toolbar-only steps
- max step count
- known system names
- system correction when local rule-based classification is stronger

Artifact:

- `steps_validated.json`

## 14. Deterministic SOP Cleanup

After validation, the pipeline runs [pipeline/sop_cleanup.py](<G:/My Drive/Video-to-SOP/pipeline/sop_cleanup.py>).

This module:

- removes obvious non-operational intro, outro, presenter, and social-banner noise
- removes weak passive review-only steps
- preserves validation checkpoints that confirm a visible output
- merges only conservative adjacent same-intent duplicates
- preserves screenshot evidence fields
- normalizes ordering metadata
- validates chronology and repairs ordering when needed
- assigns phase labels to each step
- keeps repeated phases in timeline order
- produces a quality score and readiness status

The cleanup function returns:

```python
{
  "steps": cleaned_steps,
  "removed_steps": removed_steps,
  "merged_steps": merged_steps,
  "phase_summary": phase_summary,
  "quality_report": quality_report,
}
```

The helper `validate_chronological_order(steps)` returns:

```python
{
  "is_chronological": bool,
  "violations": list[dict],
}
```

### Ordering Metadata

Cleanup preserves or infers:

- `original_step_number`
- `source_event_index`
- `start_time_seconds`
- `end_time_seconds`
- `screen_state`

### Chronology Rule

Chronology is the top invariant:

- cleanup may remove steps
- cleanup may merge steps
- cleanup may assign phase labels
- cleanup must never reorder the actual process into cleaner-looking phase buckets

Ordering precedence is:

1. `start_time_seconds`
2. `source_event_index`
3. `original_step_number`

If chronology is broken before cleanup:

- steps are repaired automatically
- the issue is recorded in the quality report
- chronology problems reduce the score

### Cleanup Removal Rules

Noise removal is universal. It targets:

- intro and title cards with no workflow action
- presenter-only screens
- outro screens
- social media follow banners
- subscribe or like prompts
- end cards
- generic visible-screen filler

Passive review removal targets weak fillers such as:

- "review the visible process screen"
- "review the worksheet data"
- "review the screen"
- "the screen is visible"

Validation checkpoints are preserved when they confirm a visible outcome, for example:

- "Validate that the report appears"
- "Verify that the exported file is available"
- "Confirm that the status changed to Posted"

### Conservative Removal Guard

If candidate cleanup would remove more than 40 percent of steps, cleanup becomes conservative:

- obvious hard noise still comes out
- borderline passive removals stop
- the quality report adds:
  - `Cleanup was conservative because too many steps were at risk of removal.`

### Merge Rules

Merge logic is universal and does not depend on fixed step numbers.

Two steps can merge only when they are:

- same system
- adjacent or near-adjacent in sequence or time
- similar in action or expected-output intent
- not hiding a distinct meaningful operation

The merge layer also checks target tokens and tries to avoid combining distinct PivotTable field operations or other clearly separate actions.

### Phase Inference

Cleanup assigns a phase label to each step. It does not globally regroup the SOP.

The phase inference is deterministic and mostly action-driven:

- generic:
  - `Open or access process`
  - `Prepare input data`
  - `Configure records or fields`
  - `Execute main action`
  - `Review and validate`
  - `Export, save, or close process`
- browser-specific when strong cues exist:
  - `Navigate to record`
  - `Update fields`
  - `Submit changes`
  - `Validate result`
  - `Export, save, or close process`
- SAP-specific when strong cues exist:
  - `Open transaction`
  - `Enter document data`
  - `Validate posting`
  - `Save or post document`
- Excel PivotTable-specific when the workflow is clearly detected:
  - `Prepare source data`
  - `Create Excel table`
  - `Create PivotTable`
  - `Configure PivotTable fields`
  - `Add calculations and formatting`
  - `Build chart and slicer`
  - `Validate final output`

### Quality Report

Cleanup produces:

- `step_count_before`
- `step_count_after`
- `removed_count`
- `merged_count`
- `low_confidence_count`
- `passive_step_count`
- `noise_step_count`
- `duplicate_candidate_count`
- `chronological_order_valid`
- `chronological_violations_count`
- `quality_score`
- `readiness`
- `warnings`

Scoring starts at 100 and subtracts for:

- remaining obvious noise
- remaining adjacent duplicate candidates
- excessive passive steps
- low-confidence volume
- very short final SOPs
- high low-confidence ratio
- chronology violations before repair
- weak generic phase structure

Readiness values are:

- `demo_ready`
- `needs_review`
- `not_ready`

Artifacts:

- `sop_cleanup.json`
- `steps_final.json`

## 15. Chronological Phase Sections

The final SOP does not globally group all steps by phase label.

Instead:

- each cleaned step keeps its own phase
- steps remain in chronological order
- a phase heading is rendered only when the phase label changes in the timeline
- the same phase can appear again later if the workflow returns to that type of work

Example:

```text
Phase A
  Step 1
  Step 2
Phase B
  Step 3
Phase C
  Step 4
Phase B
  Step 5
```

This behavior matters because process documentation must reflect the real sequence, not a tidied abstraction.

## 16. DOCX Export

The DOCX is rendered from cleaned steps only.

It includes:

- summary
- prerequisites
- assumptions
- evidence warnings
- chronological phase sections
- screenshot evidence
- confidence indicators
- low-confidence checklist
- cleanup and quality report appendix
- job metadata appendix

The cleanup appendix includes:

- original step count
- cleaned step count
- removed count
- merged count
- chronological order validity
- chronology violation count
- quality score
- readiness
- cleanup warnings
- removed steps
- merged steps

## 17. Streamlit Completion View

After job completion, the UI surfaces:

- final step count
- original step count
- cleaned step count
- removed count
- merged count
- quality score
- readiness label
- chronology validity and detected violation count
- segmentation diagnostics

This is the current user-facing quality gate for deciding whether the SOP is ready to use, needs manual review, or should be treated as not ready.
