from __future__ import annotations

import base64
import json
import os
import re
import time
from pathlib import Path
from typing import Any


GENERATION_PROMPT = """You generate business SOP steps from screen-recording evidence.

Rules:
- Do not hallucinate clicks, typed values, names, or outcomes.
- Only describe what is visible in screenshots and OCR.
- If uncertain, use conservative generic actions like Open, Display, Apply filter, Review, Export, or Save.
- Use business process language, not toolbar or menu noise.
- Keep each action concise and usable by a new employee.
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
    for event in events:
        compact_events.append(
            {
                "event_id": event["event_id"],
                "start_time_sec": round(float(event.get("start_time_sec", event.get("time_sec", 0))), 1),
                "end_time_sec": round(float(event.get("end_time_sec", event.get("time_sec", 0))), 1),
                "system_rule_guess": event.get("system", "Other"),
                "action_hint": event.get("action_hint", "review"),
                "diff_score": round(float(event.get("diff_score", 0)), 4),
                "ocr": (event.get("clean_text") or "")[:1200],
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


def _fallback_action(event: dict[str, Any]) -> dict[str, Any]:
    system = event.get("system") or "Other"
    text = (event.get("clean_text") or "").lower()
    hint = event.get("action_hint", "")
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
        action = "Review or update the visible spreadsheet data."
        expected = "The spreadsheet shows the relevant working data."
    elif system == "SAP":
        action = "Open or review the visible SAP transaction screen."
        expected = "The SAP screen displays the relevant process information."
    else:
        action = "Review the visible process screen."
        expected = "The relevant process information is available on screen."
    return {
        "event_id": event["event_id"],
        "system": system,
        "action": action,
        "expected_output": expected,
        "confidence": "low" if not event.get("clean_text") else "medium",
    }


def generate_steps(
    events: list[dict[str, Any]],
    batch_size: int = 9,
    model: str | None = None,
    max_calls: int | None = None,
    include_context_images: bool = True,
) -> list[dict[str, Any]]:
    model = model or os.getenv("OPENAI_MODEL", "gpt-5.5")
    use_openai = bool(os.getenv("OPENAI_API_KEY"))
    all_steps: list[dict[str, Any]] = []

    calls_used = 0
    for start in range(0, len(events), batch_size):
        batch = events[start : start + batch_size]
        generated: list[dict[str, Any]] = []
        if use_openai and (max_calls is None or calls_used < max_calls):
            calls_used += 1
            try:
                generated = _call_openai(batch, model=model, include_context_images=include_context_images)
            except Exception:
                generated = []
        if not generated:
            generated = [_fallback_action(event) for event in batch]

        by_event = {int(item.get("event_id", -1)): item for item in generated if str(item.get("event_id", "")).isdigit()}
        for event in batch:
            item = by_event.get(int(event["event_id"])) or _fallback_action(event)
            all_steps.append(
                {
                    "event_id": int(event["event_id"]),
                    "system": item.get("system") or event.get("system") or "Other",
                    "action": str(item.get("action") or "").strip() or _fallback_action(event)["action"],
                    "expected_output": str(item.get("expected_output") or "").strip()
                    or _fallback_action(event)["expected_output"],
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
                    "action_hint": event.get("action_hint", "review"),
                    "rule_system": event.get("system", "Other"),
                }
            )

    return all_steps[:40]
