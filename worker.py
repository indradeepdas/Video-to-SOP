from __future__ import annotations

import json
import traceback
from pathlib import Path

from pipeline.config import DEFAULT_PROFILE, estimate_job_cost, get_profile, profile_to_dict
from pipeline.docx_export import export_docx
from pipeline.generate import generate_steps
from pipeline.segmentation import segment_frames, segmentation_report
from pipeline.validate import group_phases, validate_steps
from pipeline.verify import verify_steps
from pipeline.video import extract_frames
from storage.jobs import get_job, update_job


def _process_name_from_file(path: str | Path) -> str:
    stem = Path(path).stem.replace("_", " ").replace("-", " ").strip()
    return " ".join(word.capitalize() for word in stem.split()) or "Recorded Process"


def _write_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


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
        update_job(db_path, job_id, status="running", progress=0.05, message="Extracting dense frame metrics")
        frames = extract_frames(
            input_path,
            frames_dir,
            interval_seconds=profile.metric_interval_seconds,
            max_frames=profile.max_metric_frames,
        )
        _write_json(artifacts_dir / "frames.json", frames)

        update_job(db_path, job_id, progress=0.24, message="Detecting adaptive screen boundaries")
        segmentation = segment_frames(
            frames,
            max_segments=profile.max_events,
            max_ocr_frames=profile.max_ocr_frames,
            ocr_dir=ocr_dir,
            ambiguous_reviews=profile.ambiguous_boundary_reviews,
            model=base_meta.get("cost_estimate", {}).get("model") or estimate_job_cost(profile)["model"],
        )
        _write_json(artifacts_dir / "frame_metrics.json", segmentation["frame_metrics"])
        _write_json(artifacts_dir / "boundary_candidates.json", segmentation["boundary_candidates"])
        _write_json(artifacts_dir / "screen_states.json", segmentation["screen_states"])
        _write_json(artifacts_dir / "event_segments.json", segmentation["event_segments"])
        _write_json(artifacts_dir / "ocr_raw.json", segmentation["ocr_results"])
        _write_json(artifacts_dir / "events.json", segmentation["event_segments"])
        _write_text(artifacts_dir / "segmentation_report.md", segmentation_report(segmentation))
        events = segmentation["event_segments"]

        reserved_gpt_calls = 1 + (1 if profile.ambiguous_boundary_reviews > 0 else 0)
        generation_call_budget = max(1, profile.max_gpt_calls - reserved_gpt_calls)

        update_job(db_path, job_id, progress=0.68, message="Generating SOP steps from segments")
        steps = generate_steps(
            events,
            batch_size=profile.batch_size,
            max_calls=generation_call_budget,
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
                    "screen_states": len(segmentation.get("screen_states", [])),
                    "boundary_candidates": len(segmentation.get("boundary_candidates", [])),
                    "ocr_frames": len(segmentation.get("ocr_results", [])),
                    "segmentation": {
                        "screen_states": len(segmentation.get("screen_states", [])),
                        "boundary_candidates": len(segmentation.get("boundary_candidates", [])),
                        "event_segments": len(events),
                        "threshold": segmentation.get("threshold_info", {}).get("threshold"),
                    },
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
                    "screen_states": len(segmentation.get("screen_states", [])),
                    "boundary_candidates": len(segmentation.get("boundary_candidates", [])),
                    "ocr_frames": len(segmentation.get("ocr_results", [])),
                    "segmentation": {
                        "screen_states": len(segmentation.get("screen_states", [])),
                        "boundary_candidates": len(segmentation.get("boundary_candidates", [])),
                        "event_segments": len(events),
                        "threshold": segmentation.get("threshold_info", {}).get("threshold"),
                    },
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
