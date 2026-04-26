# Pipeline Details

The pipeline is optimized for business SOP generation. It deliberately avoids trying to understand every pixel of every frame; instead it detects stable screen states and converts those states into evidence-backed task steps.

## 1. Upload

The user uploads a recording in Streamlit. The file is saved as:

```text
jobs/{job_id}/input.mp4
```

The job record stores process name, department/system notes, target audience, selected quality profile, and cost estimate.

## 2. Dense Frame Metrics

OpenCV samples the video for local boundary detection. Balanced mode uses a 1 second metric interval and caps metric frames at 2800.

Each metric frame stores:

- `frame_id`
- `time_sec`
- `path`
- dimensions
- grayscale visual `diff_score`
- perceptual `image_hash`

Frames are resized to a maximum width of 1280 pixels.

## 3. Adaptive Boundary Detection

The segmentation engine computes a boundary score between adjacent sampled frames using:

- pixel absolute difference
- SSIM structural change
- edge-map change
- perceptual hash distance

It then computes median/MAD and percentile thresholds for each video. Hysteresis prevents a noisy moment from producing multiple adjacent task boundaries.

## 4. Screen-State Segmentation

Boundary candidates are converted into `EventSegment` objects. Each segment stores:

- `start_time_sec`
- `end_time_sec`
- `before_frame`
- `entry_frame`
- `stable_frame`
- `after_frame`
- `boundary_score`
- `screen_state_id`
- `confidence_components`

Screen states combine system class, perceptual hash, OCR tokens, and boundary evidence after enrichment. Recurring screens can reappear later without being globally removed as duplicates.

## 5. OCR

OCR is capped by profile. Balanced mode runs OCR on at most 60 segment evidence frames.

When Tesseract is available:

- a preprocessed OCR image is written under `jobs/{job_id}/ocr`
- text is extracted with two fast page segmentation modes
- the longer result is kept

When Tesseract is unavailable, the job continues. Segment confidence will usually be lower when both OCR and model vision evidence are weak.

## 6. OCR Cleaning

Cleaning removes common UI noise:

- menu names
- toolbar labels
- timestamps
- repeated short lines
- decorative separator text

It keeps business terms such as supplier, invoice, payment, posting, Excel, export, status, account, tax, and reconciliation.

## 7. System Classification

Classification is rule-based for speed and cost control.

Supported systems:

- SAP
- Excel
- Email
- Slack/Teams
- Browser
- PDF
- File Explorer
- Other

The model can still improve wording, but validation prevents obvious SAP/Excel mismatches when local evidence is stronger.

## 8. OCR/System Segment Enrichment

OCR text is attached back to each segment. Boundary scores are enriched with:

- OCR text delta
- system transition
- local action hint
- original visual boundary score

Action hints include filter, export, data entry, review, post/save, and navigation.

## 9. Scroll Collapse And Event Pruning

Scroll-only segments are collapsed when they have the same system, similar OCR, and weak boundary evidence. Empty OCR is not allowed to create false similarity by itself.

Balanced mode keeps at most 40 final event segments.

## 10. Optional Ambiguous-Boundary Review

Balanced and Highest accuracy profiles can send a capped set of uncertain adjacent segment pairs to GPT vision. GPT may mark a pair as `keep` or `merge`.

This happens only after local segmentation and pruning. It is not the primary video segmentation engine.

## 11. SOP Generation

Event segments are sent to GPT in compact batches. Balanced mode uses batches of 9 and caps total GPT calls at 6, reserving budget for ambiguous-boundary review and risky-step verification.

The prompt instructs the model to:

- treat each event as one possible SOP step
- use stable segment evidence first
- avoid hallucinated clicks or values
- use generic actions when uncertain
- return JSON only

If the model fails or returns invalid JSON, the batch falls back to local step wording.

## 12. Risk Verification

Risk rules flag steps when:

- confidence is not high
- exact values appear
- specific actions like click, type, save, post, or submit appear
- model system and local system disagree

Only capped risky rows are verified. Verification includes screenshot evidence where available.

## 13. Validation

Validation enforces:

- no duplicate steps
- no toolbar-only steps
- max step count
- known system names
- local system correction for obvious mismatches

The app does not create fake steps to reach a minimum count.

## 14. SOP Cleanup And Quality Control

After verification and validation, Video2SOP runs a deterministic cleanup layer. This stage does not call OpenAI.

It removes obvious non-operational noise such as presenter outros, social banners, YouTube end cards, and generic visible-screen review steps. It also removes weak passive review-only steps unless they are true validation checkpoints.

Adjacent same-intent steps are merged conservatively when they have the same system, overlapping output, close evidence timing, and high token similarity. Distinct operational steps such as adding different PivotTable fields are preserved.

The cleanup stage assigns deterministic business phases, writes a quality score, and marks readiness as `demo_ready`, `needs_review`, or `not_ready`.

Artifacts:

- `steps_validated.json`: verified and schema-valid steps before cleanup.
- `sop_cleanup.json`: removed steps, merged steps, phase summary, and quality report.
- `steps_final.json`: final cleaned steps used in the DOCX.

## 15. Phase Grouping

Steps are grouped into:

- Access system
- Extract data
- Process in Excel
- Validate
- Post / Save

Grouping is rule-based and uses system plus action text.

## 16. DOCX Export

The final DOCX includes:

- summary
- target audience
- prerequisites
- assumptions
- evidence warnings
- phase-grouped steps
- screenshots with segment timestamp range
- confidence indicators
- low-confidence review checklist
- cleanup and quality report appendix
- job metadata appendix
