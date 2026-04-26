from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def load_json(path: Path, default):
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    if len(sys.argv) != 2:
        print("Usage: python scripts/evaluate_job.py jobs\\<job_id>")
        return 2
    job_dir = Path(sys.argv[1])
    artifacts = job_dir / "artifacts"
    if not artifacts.exists():
        print(f"Artifact folder not found: {artifacts}")
        return 2

    events = load_json(artifacts / "event_segments.json", [])
    generated = load_json(artifacts / "steps_generated.json", [])
    validated = load_json(artifacts / "steps_validated.json", [])
    final = load_json(artifacts / "steps_final.json", [])
    cleanup = load_json(artifacts / "sop_cleanup.json", {})
    ocr = load_json(artifacts / "ocr_raw.json", [])
    quality = cleanup.get("quality_report") or {}

    sources = Counter(step.get("generation_source", "unknown") for step in generated)
    diagnostic = sum(1 for step in final if step.get("diagnostic_only") or step.get("generation_source") == "diagnostic_fallback")
    generic_review = sum(1 for step in final if str(step.get("action", "")).lower().startswith("review "))
    operational = quality.get("operational_action_count")
    if operational is None:
        operational = len(final) - diagnostic - generic_review

    print(f"Job: {job_dir}")
    print(f"Events: {len(events)}")
    print(f"Generated steps: {len(generated)}")
    print(f"Validated steps: {len(validated)}")
    print(f"Final steps: {len(final)}")
    print(f"Generation sources: {dict(sources)}")
    print(f"OCR frames: {len(ocr)}")
    print(f"OCR non-empty frames: {sum(1 for row in ocr if str(row.get('raw_text') or '').strip())}")
    print(f"Generation mode: {quality.get('generation_mode', 'unknown')}")
    print(f"Operational actions: {operational}")
    print(f"Generic reviews: {quality.get('generic_review_count', generic_review)}")
    print(f"Diagnostic steps: {quality.get('diagnostic_step_count', diagnostic)}")
    print(f"Semantic coverage: {quality.get('semantic_coverage_score', 'unknown')}")
    print(f"Quality score: {quality.get('quality_score', 'unknown')}")
    print(f"Readiness: {quality.get('readiness', 'unknown')}")
    blockers = quality.get("readiness_blockers") or []
    if blockers:
        print("Readiness blockers:")
        for blocker in blockers:
            print(f"- {blocker}")
    warnings = quality.get("warnings") or []
    if warnings:
        print("Warnings:")
        for warning in warnings:
            print(f"- {warning}")

    if quality.get("readiness") == "demo_ready" and quality.get("diagnostic_step_count", diagnostic):
        print("Invalid demo_ready: diagnostic fallback steps remain.")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
