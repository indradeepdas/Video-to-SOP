from __future__ import annotations

import argparse
import os
import shutil
import sys
import uuid
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

if "--use-openai" not in sys.argv:
    os.environ["VIDEO2SOP_DISABLE_OPENAI"] = "1"

from scripts.create_demo_video import build_demo_video
from storage.jobs import create_job, get_job, init_db
from worker import run_job


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Video2SOP on a bundled synthetic demo video.")
    parser.add_argument("--use-openai", action="store_true", help="Allow OpenAI calls when OPENAI_API_KEY is configured.")
    parser.add_argument("--keep", action="store_true", help="Keep any existing demo job directory with the same id.")
    args = parser.parse_args()

    db = ROOT / "storage" / "jobs.sqlite3"
    job_id = "demo_" + uuid.uuid4().hex[:8]
    job_dir = ROOT / "jobs" / job_id
    if job_dir.exists() and not args.keep:
        shutil.rmtree(job_dir)
    job_dir.mkdir(parents=True, exist_ok=True)
    video_path = build_demo_video(job_dir / "input.mp4")

    init_db(db)
    create_job(
        db,
        job_id,
        str(video_path),
        {
            "filename": "video2sop_demo_customer_update.mp4",
            "process_name": "Update Customer Record And Export Activity Report",
            "process_name_source": "user",
            "department_notes": "Demo browser workflow",
            "target_audience": "New employee",
            "quality_profile": {"name": "Balanced"},
        },
    )
    run_job(job_id, job_dir, db)
    job = get_job(db, job_id) or {}
    meta = job.get("meta") or {}
    quality = meta.get("cleanup_report") or {}
    output_path = Path(job.get("output_path") or "")

    print(f"Job id: {job_id}")
    print(f"Status: {job.get('status')}")
    print(f"DOCX: {output_path if output_path.exists() else 'not produced'}")
    print(f"Generation mode: {quality.get('generation_mode', meta.get('generation_mode', 'unknown'))}")
    print(f"Readiness: {quality.get('readiness', meta.get('readiness', 'unknown'))}")
    print(f"Steps: {quality.get('step_count_after', meta.get('steps', 'unknown'))}")
    blockers = quality.get("readiness_blockers") or []
    if blockers:
        print("Readiness blockers:")
        for blocker in blockers[:8]:
            print(f"- {blocker}")
    if job.get("status") != "complete" or not output_path.exists():
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
