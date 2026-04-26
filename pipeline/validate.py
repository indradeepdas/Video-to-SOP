from __future__ import annotations

import re
from typing import Any


TOOLBAR_ONLY = re.compile(r"^\s*(file|edit|view|home|share|search|back|forward|refresh|toolbar|menu)\b", re.I)
KNOWN_SYSTEMS = {"SAP", "Excel", "Email", "Slack/Teams", "Browser", "PDF", "File Explorer", "Other"}


def _norm(text: str) -> str:
    return re.sub(r"\W+", " ", text.lower()).strip()


def validate_steps(steps: list[dict[str, Any]], max_steps: int = 40) -> list[dict[str, Any]]:
    valid = []
    seen = set()
    for step in steps:
        action = str(step.get("action") or "").strip()
        expected = str(step.get("expected_output") or "").strip()
        if not action or TOOLBAR_ONLY.match(action):
            continue
        signature = _norm(f"{step.get('system')} {action} {expected}")[:140]
        if signature in seen:
            continue
        seen.add(signature)

        system = step.get("system") or step.get("rule_system") or "Other"
        rule_system = step.get("rule_system")
        if system not in KNOWN_SYSTEMS:
            system = rule_system if rule_system in KNOWN_SYSTEMS else "Other"
        confidence = step.get("confidence") if step.get("confidence") in {"high", "medium", "low"} else "medium"
        if rule_system in KNOWN_SYSTEMS - {"Other"} and system != rule_system:
            system = rule_system
            confidence = "medium" if confidence == "high" else confidence

        valid.append(
            {
                **step,
                "step_number": len(valid) + 1,
                "system": system,
                "action": action,
                "expected_output": expected,
                "confidence": confidence,
                "risky": bool(step.get("risky")),
                "verified": bool(step.get("verified")),
            }
        )
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
