# Pipeline Details

The pipeline is optimized for business SOP generation. It deliberately avoids trying to understand every video frame.

## 1. Upload

The user uploads a recording in Streamlit. The file is saved as:

```text
jobs/{job_id}/input.mp4
```

The job record stores process name, department/system notes, target audience, selected quality profile, and cost estimate.

## 2. Frame Extraction

OpenCV samples the video at the profile interval. Balanced mode samples every 4.5 seconds and caps extraction at 850 frames.

Each frame stores:

- `frame_id`
- `time_sec`
- `path`
- image dimensions
- grayscale visual `diff_score`
- perceptual `image_hash`

Frames are resized to a maximum width of 1280 pixels.

## 3. Representative Selection

Selection keeps first and last frames, then combines:

- evenly spaced frames
- high-change frames
- duplicate rejection by perceptual hash
- minimum time gap enforcement

Balanced mode selects at most 80 frames.

## 4. OCR

OCR is capped by profile. Balanced mode runs OCR on at most 60 frames.

When Tesseract is available:

- a preprocessed OCR image is written under `jobs/{job_id}/ocr`
- text is extracted with two fast page segmentation modes
- the longer result is kept

When Tesseract is unavailable, the step records `ocr_available: false` and continues.

## 5. OCR Cleaning

Cleaning removes common UI noise:

- menu names
- toolbar labels
- timestamps
- repeated short lines
- decorative separator text

It keeps business terms such as supplier, invoice, payment, posting, Excel, export, status, account, tax, and reconciliation.

## 6. System Classification

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

The model can still override wording, but validation prevents obvious SAP/Excel mismatches when local evidence is stronger.

## 7. Event Clustering

The clustering stage merges near-duplicate adjacent frames and rejects scroll-only noise. It preserves system transitions, even if OCR is weak.

Each event stores:

- `before_frame`
- `evidence_frame`
- `after_frame`
- `start_time_sec`
- `end_time_sec`
- visual change score
- OCR text
- system guess
- local `action_hint`

Action hints include filter, export, data entry, review, post/save, and navigation.

## 8. Event Pruning

Events are scored using:

- business action terms
- visual change
- system classification
- text richness
- system transitions
- action hints

Balanced mode keeps at most 40 candidate events.

## 9. SOP Generation

Events are sent to GPT in compact batches. Balanced mode uses batches of 9 and caps total GPT calls at 6.

The prompt instructs the model to:

- only describe visible evidence
- avoid hallucinated clicks or values
- use generic actions when uncertain
- return JSON only

If the model fails or returns invalid JSON, the batch falls back to local step wording.

## 10. Risk Verification

Risk rules flag steps when:

- confidence is not high
- exact values appear
- specific actions like click, type, save, post, or submit appear
- model system and local system disagree

Only capped risky rows are verified. Verification includes screenshot evidence where available.

## 11. Validation

Validation enforces:

- no duplicate steps
- no toolbar-only steps
- max step count
- known system names
- local system correction for obvious mismatches

The app does not create fake steps to reach a minimum count.

## 12. Phase Grouping

Steps are grouped into:

- Access system
- Extract data
- Process in Excel
- Validate
- Post / Save

Grouping is rule-based and uses system plus action text.

## 13. DOCX Export

The final DOCX includes:

- summary
- target audience
- prerequisites
- assumptions
- evidence warnings
- phase-grouped steps
- screenshots
- confidence indicators
- low-confidence review checklist
- job metadata appendix
