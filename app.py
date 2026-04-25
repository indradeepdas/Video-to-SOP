from __future__ import annotations

import os
import threading
import time
import uuid
from pathlib import Path

import streamlit as st

from pipeline.config import DEFAULT_PROFILE, PROFILES, estimate_job_cost, get_profile, model_name, profile_to_dict
from storage.jobs import create_job, get_job, init_db, list_jobs
from worker import run_job


BASE_DIR = Path(__file__).resolve().parent
JOBS_DIR = BASE_DIR / "jobs"
DB_PATH = BASE_DIR / "storage" / "jobs.sqlite3"


def _start_worker(job_id: str, job_dir: Path) -> None:
    thread = threading.Thread(target=run_job, args=(job_id, job_dir, DB_PATH), daemon=True)
    thread.start()


def _format_status(job: dict) -> str:
    progress = int(float(job.get("progress") or 0) * 100)
    message = job.get("message") or job.get("status", "")
    return f"{progress}% - {message}"


def main() -> None:
    st.set_page_config(page_title="Video2SOP Fast Mode", layout="wide")
    init_db(DB_PATH)
    JOBS_DIR.mkdir(parents=True, exist_ok=True)

    st.title("Video2SOP Fast Mode")
    st.caption("Upload a screen recording and generate a screenshot-backed SOP DOCX.")

    with st.sidebar:
        st.subheader("Configuration")
        model = model_name()
        st.text_input("OpenAI model", value=model, disabled=True)
        st.write("OpenAI:", "configured" if os.getenv("OPENAI_API_KEY") else "not configured; fallback mode")
        st.write("OCR:", "Tesseract via pytesseract when installed")

    st.subheader("Process details")
    process_name = st.text_input("Process name", placeholder="Example: Vendor invoice review and export")
    col_meta_a, col_meta_b = st.columns(2)
    with col_meta_a:
        department_notes = st.text_input("Department / system notes", placeholder="Example: AP team, SAP + Excel")
    with col_meta_b:
        target_audience = st.text_input("Target audience", value="New employee")

    profile_name = st.selectbox(
        "Quality profile",
        options=list(PROFILES.keys()),
        index=list(PROFILES.keys()).index(DEFAULT_PROFILE),
        help="Balanced is designed for strong SOP quality while keeping API calls and image inputs capped.",
    )
    profile = get_profile(profile_name)
    estimate = estimate_job_cost(profile, use_openai=bool(os.getenv("OPENAI_API_KEY")))
    st.caption(
        "Estimated max API use: "
        f"{estimate['max_calls']} GPT calls, {estimate['image_count']} low-detail images, "
        f"about ${estimate['estimated_cost_usd']:.4f}. {estimate['pricing_note']}"
    )

    upload = st.file_uploader("Upload screen recording", type=["mp4", "mov", "mkv", "avi"])
    col_a, col_b = st.columns([1, 3])
    with col_a:
        process = st.button("Generate SOP", type="primary", disabled=upload is None)

    if process and upload is not None:
        job_id = uuid.uuid4().hex[:12]
        job_dir = JOBS_DIR / job_id
        job_dir.mkdir(parents=True, exist_ok=True)
        input_path = job_dir / "input.mp4"
        with input_path.open("wb") as handle:
            handle.write(upload.getbuffer())
        metadata = {
            "filename": upload.name,
            "process_name": process_name.strip() or Path(upload.name).stem.replace("_", " ").replace("-", " ").title(),
            "department_notes": department_notes.strip(),
            "target_audience": target_audience.strip() or "New employee",
            "quality_profile": profile_to_dict(profile),
            "cost_estimate": estimate,
        }
        create_job(DB_PATH, job_id, str(input_path), meta=metadata)
        st.session_state["active_job_id"] = job_id
        _start_worker(job_id, job_dir)
        st.success(f"Job started: {job_id}")

    active_job_id = st.session_state.get("active_job_id")
    if active_job_id:
        job = get_job(DB_PATH, active_job_id)
        if job:
            st.subheader("Current job")
            st.progress(float(job.get("progress") or 0), text=_format_status(job))
            status = job.get("status")
            if status in {"queued", "running"}:
                time.sleep(2)
                st.rerun()
            elif status == "complete":
                if job.get("error"):
                    st.warning("The SOP was produced using fallback handling. Review low-confidence steps.")
                output_path = job.get("output_path")
                if output_path and Path(output_path).exists():
                    with open(output_path, "rb") as handle:
                        st.download_button(
                            "Download SOP DOCX",
                            data=handle,
                            file_name=f"video2sop_{active_job_id}.docx",
                            mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                        )
                    meta = job.get("meta") or {}
                    st.write(f"Steps: {meta.get('steps', 'unknown')}")
                    if meta.get("warnings"):
                        st.warning(" ".join(meta["warnings"]))
            elif status == "failed":
                st.error("The job failed before a DOCX could be produced.")
                with st.expander("Error details"):
                    st.code(job.get("error") or "Unknown error")

    st.subheader("Recent jobs")
    rows = list_jobs(DB_PATH, limit=10)
    if rows:
        for job in rows:
            cols = st.columns([2, 2, 4, 2])
            cols[0].write(job["id"])
            cols[1].write(job["status"])
            cols[2].write(job.get("message", ""))
            output_path = job.get("output_path")
            if output_path and Path(output_path).exists():
                with open(output_path, "rb") as handle:
                    cols[3].download_button(
                        "Download",
                        data=handle,
                        file_name=f"video2sop_{job['id']}.docx",
                        mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                        key=f"download_{job['id']}",
                    )
    else:
        st.info("No jobs yet.")


if __name__ == "__main__":
    main()
