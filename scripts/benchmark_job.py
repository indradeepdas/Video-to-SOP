from __future__ import annotations

import argparse
import json
import shutil
import sys
import time
import uuid
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from storage.jobs import create_job, get_job, init_db
from worker import run_job


def _artifact_count(job_dir: Path, name: str) -> int | str:
    path = job_dir / "artifacts" / name
    if not path.exists():
        return "unknown"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return "unknown"
    return len(payload) if isinstance(payload, list) else "unknown"


def main() -> int:
    parser = argparse.ArgumentParser(description="Run a Video2SOP benchmark job and print quality/runtime metrics.")
    parser.add_argument("video", help="Path to a screen-recording video.")
    parser.add_argument("--profile", default="Showcase fast", help="Quality profile name.")
    parser.add_argument("--process-name", default="", help="Optional human-readable process name.")
    args = parser.parse_args()

    source_video = Path(args.video)
    if not source_video.exists():
        print(f"Video not found: {source_video}")
        return 2

    job_id = "bench_" + uuid.uuid4().hex[:8]
    job_dir = ROOT / "jobs" / job_id
    job_dir.mkdir(parents=True, exist_ok=True)
    input_path = job_dir / "input.mp4"
    shutil.copy2(source_video, input_path)

    db_path = ROOT / "storage" / "jobs.sqlite3"
    init_db(db_path)
    create_job(
        db_path,
        job_id,
        str(input_path),
        {
            "filename": source_video.name,
            "upload_name": source_video.name,
            "process_name": args.process_name,
            "process_name_source": "user" if args.process_name else "derived",
            "target_audience": "New employee",
            "quality_profile": {"name": args.profile},
        },
    )

    started_at = time.perf_counter()
    run_job(job_id, job_dir, db_path)
    elapsed = round(time.perf_counter() - started_at, 3)
    job = get_job(db_path, job_id) or {}
    meta = job.get("meta") or {}
    quality = meta.get("cleanup_report") or {}
    timings = meta.get("stage_timings") or {}

    print(f"Job id: {job_id}")
    print(f"Status: {job.get('status')}")
    print(f"DOCX: {job.get('output_path')}")
    print(f"Elapsed seconds: {elapsed}")
    print(f"Stage timings: {timings}")
    print(f"Frames: {meta.get('frames', 'unknown')}")
    print(f"Events: {meta.get('event_segments', 'unknown')}")
    print(f"Raw generated steps: {_artifact_count(job_dir, 'steps_generated.json')}")
    print(f"Validated steps: {_artifact_count(job_dir, 'steps_validated.json')}")
    print(f"Cleaned steps: {quality.get('step_count_after', meta.get('cleaned_steps', 'unknown'))}")
    print(f"Steps per minute: {quality.get('workflow_density_score', 'unknown')}")
    print(f"Phase errors: {quality.get('phase_error_count', 'unknown')}")
    print(f"Long single-step segments: {quality.get('long_segment_single_step_count', 'unknown')}")
    print(f"Readiness: {quality.get('readiness', meta.get('readiness', 'unknown'))}")
    blockers = quality.get("readiness_blockers") or []
    if blockers:
        print("Readiness blockers:")
        for blocker in blockers:
            print(f"- {blocker}")

    return 0 if job.get("status") == "complete" else 1


if __name__ == "__main__":
    raise SystemExit(main())
