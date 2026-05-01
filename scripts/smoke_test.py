from __future__ import annotations

import os
import shutil
import sys
import uuid
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ["VIDEO2SOP_DISABLE_OPENAI"] = "1"

from storage.jobs import create_job, get_job, init_db
from worker import run_job


def build_video(video_path: Path) -> None:
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    writer = cv2.VideoWriter(str(video_path), fourcc, 1.0, (960, 540))
    screens = [
        ("SAP Invoice Monitor", "Open SAP invoice worklist\nSupplier and payment terms visible"),
        ("SAP Invoice Monitor", "Apply filter for pending invoices\nCompany code and posting date fields visible"),
        ("Excel Reconciliation", "Export results to Excel\nColumns: Supplier, Invoice, Amount, Status"),
        ("Excel Reconciliation", "Validate invoice amounts and statuses\nMark reviewed rows"),
        ("SAP Posting", "Save or post reviewed transaction\nDocument status visible"),
    ]
    for title, body in screens:
        frame = np.full((540, 960, 3), 245, dtype=np.uint8)
        cv2.rectangle(frame, (0, 0), (960, 70), (32, 88, 120), -1)
        cv2.putText(frame, title, (35, 45), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (255, 255, 255), 2)
        y = 150
        for line in body.split("\n"):
            cv2.putText(frame, line, (60, y), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (20, 20, 20), 2)
            y += 70
        for _ in range(2):
            writer.write(frame)
    writer.release()


def main() -> int:
    db = ROOT / "storage" / "jobs.sqlite3"
    job_id = "smoke_" + uuid.uuid4().hex[:8]
    job_dir = ROOT / "jobs" / job_id
    if job_dir.exists():
        shutil.rmtree(job_dir)
    job_dir.mkdir(parents=True)
    video_path = job_dir / "input.mp4"
    build_video(video_path)

    init_db(db)
    create_job(
        db,
        job_id,
        str(video_path),
        {
            "filename": "smoke.mp4",
            "process_name": "Smoke Test Invoice Process",
            "department_notes": "Test AP team",
            "target_audience": "New employee",
            "quality_profile": {"name": "Balanced"},
        },
    )
    run_job(job_id, job_dir, db)
    job = get_job(db, job_id)
    output_path = Path(job.get("output_path") or "")
    if not job or job.get("status") != "complete" or not output_path.exists():
        print(job)
        return 1
    cleanup = (job.get("meta") or {}).get("cleanup_report") or {}
    required_cleanup_fields = {
        "event_segments",
        "coverage_ratio_before_cleanup",
        "coverage_ratio_after_cleanup",
        "coverage_guardrail_triggered",
        "coverage_warnings",
        "readiness_blockers",
        "operational_checkpoint_count",
        "passive_filler_removed_count",
        "generation_mode",
        "generation_source_counts",
        "ocr_available",
        "ocr_non_empty_count",
        "semantic_coverage_score",
        "operational_action_count",
        "generic_review_count",
        "diagnostic_step_count",
    }
    if not required_cleanup_fields.issubset(cleanup):
        print(job)
        return 1
    if cleanup.get("coverage_guardrail_triggered") and cleanup.get("readiness") == "demo_ready":
        print(job)
        return 1
    print(f"Smoke test complete: {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
