from __future__ import annotations

import re
from typing import Any


TOOLBAR_ONLY = re.compile(r"^\s*(file|edit|view|home|share|search|back|forward|refresh|toolbar|menu)\b", re.I)
KNOWN_SYSTEMS = {"SAP", "Excel", "Email", "Slack/Teams", "Browser", "PDF", "File Explorer", "Other"}


def _norm(text: str) -> str:
    return re.sub(r"\W+", " ", text.lower()).strip()


def _coerce_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except Exception:
        return None


def _coerce_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except Exception:
        return None


def _generic_review(action: str, expected: str) -> bool:
    text = _norm(f"{action} {expected}")
    return text in {
        "review the visible process screen the relevant process information is available on screen",
        "review the visible process screen the expected screen is displayed",
    }


def _nearby_duplicate(left: dict[str, Any], right: dict[str, Any]) -> bool:
    left_action = str(left.get("action") or "").strip()
    right_action = str(right.get("action") or "").strip()
    left_expected = str(left.get("expected_output") or "").strip()
    right_expected = str(right.get("expected_output") or "").strip()
    if left.get("system") != right.get("system"):
        return False
    if _norm(left_action) != _norm(right_action) or _norm(left_expected) != _norm(right_expected):
        return False

    same_screenshot = bool(left.get("screenshot") and left.get("screenshot") == right.get("screenshot"))
    same_state = bool(left.get("screen_state_id") and left.get("screen_state_id") == right.get("screen_state_id"))
    has_evidence_key = bool(left.get("screenshot") or right.get("screenshot") or left.get("screen_state_id") or right.get("screen_state_id"))
    left_event = _coerce_int(left.get("source_event_index") or left.get("event_id"))
    right_event = _coerce_int(right.get("source_event_index") or right.get("event_id"))
    event_close = left_event is not None and right_event is not None and abs(right_event - left_event) <= 1
    left_time = _coerce_float(left.get("start_time_sec") or left.get("time_sec"))
    right_time = _coerce_float(right.get("start_time_sec") or right.get("time_sec"))
    time_close = left_time is not None and right_time is not None and abs(right_time - left_time) <= 12

    if _generic_review(left_action, left_expected):
        return same_screenshot or same_state
    if not has_evidence_key:
        return event_close or time_close
    return (same_screenshot or same_state) and (event_close or time_close)


def validate_steps(steps: list[dict[str, Any]], max_steps: int = 40) -> list[dict[str, Any]]:
    valid = []
    for step in steps:
        action = str(step.get("action") or "").strip()
        expected = str(step.get("expected_output") or "").strip()
        if not action or TOOLBAR_ONLY.match(action):
            continue

        system = step.get("system") or step.get("rule_system") or "Other"
        rule_system = step.get("rule_system")
        if system not in KNOWN_SYSTEMS:
            system = rule_system if rule_system in KNOWN_SYSTEMS else "Other"
        confidence = step.get("confidence") if step.get("confidence") in {"high", "medium", "low"} else "medium"
        if rule_system in KNOWN_SYSTEMS - {"Other"} and system != rule_system:
            system = rule_system
            confidence = "medium" if confidence == "high" else confidence

        normalized = {
            **step,
            "step_number": len(valid) + 1,
            "system": system,
            "action": action,
            "expected_output": expected,
            "confidence": confidence,
            "risky": bool(step.get("risky")),
            "verified": bool(step.get("verified")),
            "source_event_index": step.get("source_event_index") or step.get("event_id"),
        }
        if valid and _nearby_duplicate(valid[-1], normalized):
            continue
        valid.append(normalized)
        if len(valid) >= max_steps:
            break
    return valid


def group_phases(steps: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    explicit_phases = [step.get("phase") for step in steps if step.get("phase")]
    if explicit_phases:
        sections: list[dict[str, Any]] = []
        current_phase = None
        for step in steps:
            phase = step.get("phase") or "Review and validate"
            if phase != current_phase:
                sections.append({"phase": phase, "steps": []})
                current_phase = phase
            sections[-1]["steps"].append(step)
        return sections

    phases = {
        "Access system": [],
        "Extract data": [],
        "Process in Excel": [],
        "Validate": [],
        "Post / Save": [],
    }
    for step in steps:
        text = f"{step.get('system', '')} {step.get('action', '')} {step.get('expected_output', '')}".lower()
        if step.get("system") == "Excel" or "spreadsheet" in text:
            phase = "Process in Excel"
        elif any(term in text for term in ["export", "extract", "download", "filter"]):
            phase = "Extract data"
        elif any(term in text for term in ["validate", "review", "confirm", "check"]):
            phase = "Validate"
        elif any(term in text for term in ["post", "save", "submit", "approve"]):
            phase = "Post / Save"
        else:
            phase = "Access system" if len(phases["Access system"]) < 4 else "Validate"
        phases[phase].append(step)
    return {phase: items for phase, items in phases.items() if items}
