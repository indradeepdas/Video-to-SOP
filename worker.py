from __future__ import annotations

import json
import traceback
from pathlib import Path

from pipeline.classify import classify_events
from pipeline.clean_ocr import clean_ocr_results
from pipeline.cluster import cluster_events, prune_events
from pipeline.config import DEFAULT_PROFILE, estimate_job_cost, get_profile, profile_to_dict
from pipeline.docx_export import export_docx
from pipeline.generate import generate_steps
from pipeline.ocr import run_ocr
from pipeline.validate import group_phases, validate_steps
from pipeline.verify import verify_steps
from pipeline.video import extract_frames, select_representative_frames
from storage.jobs import get_job, update_job


def _process_name_from_file(path: str | Path) -> str:
    stem = Path(path).stem.replace("_", " ").replace("-", " ").strip()
    return " ".join(word.capitalize() for word in stem.split()) or "Recorded Process"


def _write_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def run_job(job_id: str, job_dir: str | Path, db_path: str | Path) -> None:
    job_dir = Path(job_dir)
    input_path = job_dir / "input.mp4"
    output_path = job_dir / "sop.docx"
    frames_dir = job_dir / "frames"
    artifacts_dir = job_dir / "artifacts"
    ocr_dir = job_dir / "ocr"
    job = get_job(db_path, job_id) or {}
    base_meta = job.get("meta") or {}
    profile_meta = base_meta.get("quality_profile") or {}
    profile = get_profile(profile_meta.get("name") or DEFAULT_PROFILE)
    process_name = base_meta.get("process_name") or _process_name_from_file(input_path)
    department_notes = base_meta.get("department_notes", "")
    target_audience = base_meta.get("target_audience", "New employee")

    def finish_meta(extra: dict) -> dict:
        merged = dict(base_meta)
        merged.update(extra)
        merged["quality_profile"] = profile_to_dict(profile)
        return merged

    try:
        update_job(db_path, job_id, status="running", progress=0.05, message="Extracting frames")
        frames = extract_frames(
            input_path,
            frames_dir,
            interval_seconds=profile.frame_interval_seconds,
            max_frames=profile.max_extracted_frames,
        )
        _write_json(artifacts_dir / "frames.json", frames)

        update_job(db_path, job_id, progress=0.22, message="Selecting representative frames")
        selected = select_representative_frames(frames, max_selected=profile.max_selected_frames)
        _write_json(artifacts_dir / "selected_frames.json", selected)

        update_job(db_path, job_id, progress=0.34, message="Running OCR")
        ocr_results = run_ocr(selected, max_frames=profile.max_ocr_frames, ocr_dir=ocr_dir)
        _write_json(artifacts_dir / "ocr_raw.json", ocr_results)

        update_job(db_path, job_id, progress=0.45, message="Cleaning OCR and classifying systems")
        cleaned = clean_ocr_results(ocr_results)
        classified = classify_events(cleaned)
        _write_json(artifacts_dir / "classified.json", classified)

        update_job(db_path, job_id, progress=0.56, message="Clustering and pruning candidate events")
        clustered = cluster_events(classified, target_max=60)
        events = prune_events(clustered, max_events=profile.max_events)
        _write_json(artifacts_dir / "events.json", events)

        update_job(db_path, job_id, progress=0.68, message="Generating SOP steps")
        steps = generate_steps(
            events,
            batch_size=profile.batch_size,
            max_calls=max(1, profile.max_gpt_calls - 1),
            include_context_images=profile.include_context_images,
        )
        _write_json(artifacts_dir / "steps_generated.json", steps)

        update_job(db_path, job_id, progress=0.80, message="Verifying risky steps")
        verified = verify_steps(steps, max_risky=profile.verify_risky_limit)
        valid_steps = validate_steps(verified, max_steps=profile.max_steps)
        if not valid_steps:
            valid_steps = validate_steps(generate_steps(events[:25], batch_size=profile.batch_size), max_steps=profile.max_steps)
        _write_json(artifacts_dir / "steps_final.json", valid_steps)

        update_job(db_path, job_id, progress=0.90, message="Building DOCX")
        warnings = []
        if len(valid_steps) < 25:
            warnings.append(
                f"Only {len(valid_steps)} evidence-backed steps were found. The SOP was not padded with invented steps."
            )
        phases = group_phases(valid_steps)
        export_docx(
            process_name,
            phases,
            output_path,
            target_audience=target_audience,
            department_notes=department_notes,
            warnings=warnings,
            job_metadata=finish_meta(
                {
                    "steps": len(valid_steps),
                    "events": len(events),
                    "frames": len(frames),
                    "selected_frames": len(selected),
                    "ocr_frames": len(ocr_results),
                    "cost_estimate": estimate_job_cost(profile),
                }
            ),
        )

        update_job(
            db_path,
            job_id,
            status="complete",
            progress=1.0,
            message="SOP ready",
            output_path=str(output_path),
            error=None,
            meta_json=finish_meta(
                {
                    "steps": len(valid_steps),
                    "events": len(events),
                    "frames": len(frames),
                    "selected_frames": len(selected),
                    "ocr_frames": len(ocr_results),
                    "warnings": warnings,
                    "cost_estimate": estimate_job_cost(profile),
                }
            ),
        )
    except Exception as exc:
        error_text = f"{exc}\n{traceback.format_exc()}"
        try:
            fallback_events = []
            if (artifacts_dir / "events.json").exists():
                fallback_events = json.loads((artifacts_dir / "events.json").read_text(encoding="utf-8"))
            elif (artifacts_dir / "classified.json").exists():
                fallback_events = json.loads((artifacts_dir / "classified.json").read_text(encoding="utf-8"))[:25]
            if fallback_events:
                steps = validate_steps(generate_steps(fallback_events, batch_size=profile.batch_size), max_steps=profile.max_steps)
                phases = group_phases(steps)
                warnings = ["The SOP was produced using fallback handling after a pipeline error."]
                if len(steps) < 25:
                    warnings.append(f"Only {len(steps)} evidence-backed steps were found; no invented padding was added.")
                export_docx(
                    process_name,
                    phases,
                    output_path,
                    target_audience=target_audience,
                    department_notes=department_notes,
                    warnings=warnings,
                    job_metadata=finish_meta({"fallback": True, "steps": len(steps)}),
                )
                update_job(
                    db_path,
                    job_id,
                    status="complete",
                    progress=1.0,
                    message="SOP ready with fallback output",
                    output_path=str(output_path),
                    error=error_text,
                    meta_json=finish_meta({"fallback": True, "steps": len(steps), "warnings": warnings}),
                )
                return
        except Exception:
            pass
        update_job(db_path, job_id, status="failed", progress=1.0, message="Job failed", error=error_text)
