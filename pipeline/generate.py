from __future__ import annotations

import base64
import json
import os
import re
import time
from pathlib import Path
from typing import Any


GENERATION_PROMPT = """You generate business SOP steps from segmented screen-recording evidence.

Rules:
- Return exactly one JSON object for every input event_id. Do not skip event_ids.
- Treat one event_id as one possible SOP step produced by the segmentation engine.
- Do not merge multiple event_ids into one conceptual SOP step.
- If a screenshot shows a dialog, pane, field configuration area, chart setup, slicer setup, or calculation setup that changes workflow state, describe that configuration action explicitly.
- Do not compress a measure-add action and a rename action unless the evidence clearly shows one combined operation.
- Prefer separate event-specific steps for actions such as adding a measure, changing a calculation, showing values as a percentage, renaming a field, inserting a chart, inserting a slicer, and applying a slicer selection when they appear across distinct events.
- Do not hallucinate clicks, typed values, names, or outcomes.
- Only describe what is visible in segment screenshots and OCR.
- Use stable_frame evidence first; before/after frames only provide context.
- If uncertain, use conservative generic actions like Open, Display, Apply filter, Review, Export, or Save.
- If an event appears operational but uncertain, produce a conservative event-specific step instead of repeating "Review the visible process screen."
- Use business process language, not toolbar or menu noise.
- Keep each action concise and usable by a new employee.
- You may make a step generic or low confidence, but do not invent missing business actions.
- Return only valid JSON matching this shape:
[
  {
    "event_id": 1,
    "system": "SAP|Excel|Email|Slack/Teams|Browser|PDF|File Explorer|Other",
    "action": "...",
    "expected_output": "...",
    "confidence": "high|medium|low"
  }
]
"""

ALLOWED_CONFIDENCE = {"high", "medium", "low"}
GENERIC_REVIEW_SIGNATURES = {
    "review the visible process screen",
    "review the process state shown",
    "review the process screen shown",
}


def _encode_image(path: str) -> str:
    with open(path, "rb") as handle:
        return base64.b64encode(handle.read()).decode("utf-8")


def _extract_json(text: str) -> list[dict[str, Any]]:
    if not text:
        raise ValueError("empty model output")
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = re.sub(r"^```(?:json)?", "", stripped).strip()
        stripped = re.sub(r"```$", "", stripped).strip()
    match = re.search(r"\[[\s\S]*\]", stripped)
    payload = match.group(0) if match else stripped
    data = json.loads(payload)
    if not isinstance(data, list):
        raise ValueError("model output is not a JSON array")
    return [item for item in data if isinstance(item, dict)]


def _image_parts_for_event(event: dict[str, Any], include_context_images: bool) -> list[tuple[str, str]]:
    keys = ["evidence_frame"]
    if include_context_images:
        keys = ["before_frame", "evidence_frame", "after_frame"]
    parts = []
    seen = set()
    for key in keys:
        path = event.get(key) or event.get("path")
        if path and path not in seen and Path(path).exists():
            seen.add(path)
            parts.append((key, path))
    return parts


def _call_openai(
    events: list[dict[str, Any]],
    model: str,
    include_context_images: bool,
    max_retries: int = 1,
) -> list[dict[str, Any]]:
    from openai import OpenAI

    client = OpenAI()
    content: list[dict[str, Any]] = [{"type": "input_text", "text": GENERATION_PROMPT}]
    compact_events = []
    for index, event in enumerate(events):
        previous_event = events[index - 1] if index > 0 else {}
        next_event = events[index + 1] if index + 1 < len(events) else {}
        compact_events.append(
            {
                "event_id": event["event_id"],
                "start_time_sec": round(float(event.get("start_time_sec", event.get("time_sec", 0))), 1),
                "end_time_sec": round(float(event.get("end_time_sec", event.get("time_sec", 0))), 1),
                "system_rule_guess": event.get("system", "Other"),
                "previous_system_rule_guess": previous_event.get("system"),
                "next_system_rule_guess": next_event.get("system"),
                "action_hint": event.get("action_hint", "review"),
                "diff_score": round(float(event.get("diff_score", 0)), 4),
                "boundary_score": round(float(event.get("boundary_score", 0)), 4),
                "screen_state_id": event.get("screen_state_id"),
                "previous_screen_state_id": previous_event.get("screen_state_id"),
                "next_screen_state_id": next_event.get("screen_state_id"),
                "ocr": (event.get("clean_text") or "")[:1200],
                "previous_ocr": (previous_event.get("clean_text") or "")[:350],
                "next_ocr": (next_event.get("clean_text") or "")[:350],
                "dense_repeated_run": bool(event.get("dense_repeated_run")),
                "ocr_blank": not bool((event.get("clean_text") or "").strip()),
            }
        )
        for image_role, image_path in _image_parts_for_event(event, include_context_images):
            try:
                image = _encode_image(image_path)
            except Exception:
                continue
            content.append(
                {
                    "type": "input_text",
                    "text": f"{image_role} screenshot for event_id {event['event_id']}:",
                }
            )
            content.append(
                {
                    "type": "input_image",
                    "image_url": f"data:image/jpeg;base64,{image}",
                    "detail": "low",
                }
            )

    content.insert(
        1,
        {
            "type": "input_text",
            "text": "Events to convert into SOP steps:\n" + json.dumps(compact_events, ensure_ascii=False),
        },
    )

    last_error: Exception | None = None
    for attempt in range(max_retries + 1):
        try:
            response = client.responses.create(
                model=model,
                input=[{"role": "user", "content": content}],
                temperature=0.2,
            )
            return _extract_json(getattr(response, "output_text", "") or "")
        except Exception as exc:
            last_error = exc
            time.sleep(1.5 * (attempt + 1))
    raise RuntimeError(f"OpenAI generation failed: {last_error}")


def _fallback_action(event: dict[str, Any], openai_failed: bool = False) -> dict[str, Any]:
    system = event.get("system") or "Other"
    text = (event.get("clean_text") or "").lower()
    hint = event.get("action_hint", "")
    event_id = int(event.get("event_id", 0) or 0)
    state = event.get("screen_state_id")
    generation_source = "local_ocr" if text.strip() else "diagnostic_fallback"
    diagnostic_only = generation_source == "diagnostic_fallback"
    if hint == "filter" or "filter" in text:
        action = "Apply or review the visible filter criteria."
        expected = "The filtered results are displayed for review."
    elif hint == "export" or "export" in text or "download" in text:
        action = "Export the displayed data."
        expected = "The data export is prepared or completed."
    elif hint == "data entry":
        action = "Enter or review the visible business fields."
        expected = "The required fields are populated or ready for validation."
    elif hint == "post/save" or "save" in text or "post" in text:
        action = "Save or post the visible transaction after review."
        expected = "The system records the transaction status."
    elif "invoice" in text or "supplier" in text or "vendor" in text:
        action = "Review the visible invoice or supplier details."
        expected = "The required business details are visible for validation."
    elif system == "Excel":
        if "pivot" in text or "field" in text or "measure" in text:
            action = "Review or configure the visible Excel analysis element."
            expected = "The Excel worksheet or analysis view reflects the visible configuration change."
        else:
            action = "Review or update the visible spreadsheet data."
            expected = "The spreadsheet shows the relevant working data."
    elif system == "SAP":
        action = "Open or review the visible SAP transaction screen."
        expected = "The SAP screen displays the relevant process information."
    elif hint == "navigation":
        action = "Open or navigate to the visible process area."
        expected = "The next process screen is available for review."
    elif state is not None:
        action = f"Review the process state shown at event {event_id}."
        expected = f"Screen state {state} is visible for the next workflow action."
    else:
        action = f"Review the visible process screen for event {event_id}."
        expected = "The relevant process information is available for chronological review."
    return {
        "event_id": event["event_id"],
        "system": system,
        "action": action,
        "expected_output": expected,
        "confidence": "low" if not event.get("clean_text") else "medium",
        "generation_source": generation_source,
        "diagnostic_only": diagnostic_only,
        "semantic_quality": "diagnostic" if diagnostic_only else "passive",
        "openai_generation_failed": openai_failed,
    }


def _looks_generic_review(action: str) -> bool:
    normalized = re.sub(r"[^a-z0-9 ]+", " ", action.lower()).strip()
    return any(normalized.startswith(signature) for signature in GENERIC_REVIEW_SIGNATURES)


def _audit_generated_steps(steps: list[dict[str, Any]], events: list[dict[str, Any]]) -> None:
    previous_signature = ""
    run_length = 0
    event_map = {int(event.get("event_id", 0)): event for event in events}
    for index, step in enumerate(steps):
        action = str(step.get("action", ""))
        signature = re.sub(r"\W+", " ", f"{step.get('system')} {action} {step.get('expected_output')}".lower()).strip()
        event = event_map.get(int(step.get("event_id", 0)), {})
        if signature == previous_signature:
            run_length += 1
        else:
            previous_signature = signature
            run_length = 1
        if run_length >= 2 and _looks_generic_review(action):
            step["weak_coverage_candidate"] = True
            step["coverage_review_required"] = True

        excel_operational_gap = (
            step.get("system") == "Excel"
            and _looks_generic_review(action)
            and (
                step.get("action_hint") in {"data entry", "filter", "post/save"}
                or float(step.get("boundary_score", 0) or 0) >= 0.18
                or any(
                    phrase in (step.get("ocr", "") or "").lower()
                    for phrase in ["field", "measure", "sum", "maximum", "percentage", "pivotchart", "slicer", "dialog", "pane"]
                )
            )
        )
        if excel_operational_gap:
            step["coverage_review_required"] = True
            step["possible_missing_operation"] = True

        previous_event = event_map.get(int(events[index - 1].get("event_id", 0))) if index > 0 and index - 1 < len(events) else {}
        next_event = event_map.get(int(events[index + 1].get("event_id", 0))) if index + 1 < len(events) else {}
        if _looks_generic_review(action) and (
            previous_event.get("screen_state_id") != event.get("screen_state_id")
            or next_event.get("screen_state_id") != event.get("screen_state_id")
        ):
            step["coverage_review_required"] = True


def generate_steps(
    events: list[dict[str, Any]],
    batch_size: int = 9,
    model: str | None = None,
    max_calls: int | None = None,
    include_context_images: bool = True,
    run_stats: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    model = model or os.getenv("OPENAI_MODEL", "gpt-5.5")
    use_openai = bool(os.getenv("OPENAI_API_KEY"))
    if run_stats is not None:
        run_stats.setdefault("openai_calls_attempted", 0)
        run_stats.setdefault("openai_calls_succeeded", 0)
        run_stats.setdefault("openai_errors", [])
    all_steps: list[dict[str, Any]] = []

    calls_used = 0
    for start in range(0, len(events), batch_size):
        batch = events[start : start + batch_size]
        generated: list[dict[str, Any]] = []
        openai_failed = False
        if use_openai and (max_calls is None or calls_used < max_calls):
            calls_used += 1
            if run_stats is not None:
                run_stats["openai_calls_attempted"] += 1
            try:
                generated = _call_openai(batch, model=model, include_context_images=include_context_images)
                if run_stats is not None:
                    run_stats["openai_calls_succeeded"] += 1
                for item in generated:
                    item["generation_source"] = "openai_vision"
                    item["diagnostic_only"] = False
                    item["semantic_quality"] = "operational"
            except Exception as exc:
                openai_failed = True
                if run_stats is not None:
                    run_stats["openai_errors"].append(str(exc))
                generated = []
        if not generated:
            generated = [_fallback_action(event, openai_failed=openai_failed) for event in batch]

        by_event = {int(item.get("event_id", -1)): item for item in generated if str(item.get("event_id", "")).isdigit()}
        for event in batch:
            item = by_event.get(int(event["event_id"])) or _fallback_action(event, openai_failed=openai_failed)
            fallback = _fallback_action(event, openai_failed=openai_failed)
            all_steps.append(
                {
                    "event_id": int(event["event_id"]),
                    "system": item.get("system") or event.get("system") or "Other",
                    "action": str(item.get("action") or "").strip() or fallback["action"],
                    "expected_output": str(item.get("expected_output") or "").strip()
                    or fallback["expected_output"],
                    "confidence": str(item.get("confidence") or "medium").lower()
                    if str(item.get("confidence") or "").lower() in ALLOWED_CONFIDENCE
                    else "medium",
                    "screenshot": event.get("evidence_frame") or event.get("path"),
                    "before_frame": event.get("before_frame"),
                    "after_frame": event.get("after_frame"),
                    "ocr": event.get("clean_text", ""),
                    "time_sec": event.get("time_sec", 0),
                    "start_time_sec": event.get("start_time_sec", event.get("time_sec", 0)),
                    "end_time_sec": event.get("end_time_sec", event.get("time_sec", 0)),
                    "boundary_score": event.get("boundary_score", 0),
                    "screen_state_id": event.get("screen_state_id"),
                    "confidence_components": event.get("confidence_components", {}),
                    "action_hint": event.get("action_hint", "review"),
                    "rule_system": event.get("system", "Other"),
                    "source_event_index": int(event["event_id"]),
                    "generation_source": item.get("generation_source") or fallback["generation_source"],
                    "diagnostic_only": bool(item.get("diagnostic_only", fallback["diagnostic_only"])),
                    "semantic_quality": item.get("semantic_quality") or fallback["semantic_quality"],
                    "openai_generation_failed": bool(item.get("openai_generation_failed") or openai_failed),
                }
            )

    _audit_generated_steps(all_steps, events)

    return all_steps[:40]
