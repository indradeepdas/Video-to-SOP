from __future__ import annotations

import base64
import json
import os
import re
import time
from pathlib import Path
from typing import Any


SPECIFIC_ACTION_RE = re.compile(r"\b(click|type|enter|press|save|post|submit|delete|approve)\b", re.I)
EXACT_VALUE_RE = re.compile(r"\b\d{4,}|\$?\d+\.\d{2}\b")


def _encode_image(path: str) -> str:
    with open(path, "rb") as handle:
        return base64.b64encode(handle.read()).decode("utf-8")


def _sanitize_risky_text(text: str) -> str:
    text = EXACT_VALUE_RE.sub("the visible value", text)
    text = re.sub(r"\b[Cc]lick\b", "Select", text)
    text = re.sub(r"\b[Tt]ype\b", "Enter", text)
    return re.sub(r"\s+", " ", text).strip()


def mark_risks(steps: list[dict[str, Any]]) -> list[dict[str, Any]]:
    marked = []
    for step in steps:
        text = f"{step.get('action', '')} {step.get('expected_output', '')}"
        risky = (
            step.get("confidence") != "high"
            or bool(SPECIFIC_ACTION_RE.search(text))
            or bool(EXACT_VALUE_RE.search(text))
            or (
                step.get("rule_system")
                and step.get("system")
                and step.get("rule_system") != "Other"
                and step.get("system") != step.get("rule_system")
            )
        )
        marked.append({**step, "risky": risky})
    return marked


def _extract_json(text: str) -> list[dict[str, Any]]:
    match = re.search(r"\[[\s\S]*\]", text.strip())
    return json.loads(match.group(0) if match else text)


def _call_verify(risky_steps: list[dict[str, Any]], model: str) -> list[dict[str, Any]]:
    from openai import OpenAI

    client = OpenAI()
    payload = [
        {
            "event_id": step["event_id"],
            "system": step["system"],
            "action": step["action"],
            "expected_output": step["expected_output"],
            "confidence": step["confidence"],
            "ocr": (step.get("ocr") or "")[:900],
        }
        for step in risky_steps
    ]
    prompt = """Rewrite risky SOP rows conservatively.
Rules:
- Remove exact values unless they are clearly a field label.
- Do not invent clicks, saves, postings, names, or numbers.
- Downgrade confidence when OCR/evidence is weak.
- Return only a JSON array with event_id, system, action, expected_output, confidence.
"""
    content: list[dict[str, Any]] = [
        {"type": "input_text", "text": prompt},
        {"type": "input_text", "text": json.dumps(payload, ensure_ascii=False)},
    ]
    for step in risky_steps:
        screenshot = step.get("screenshot")
        if screenshot and Path(screenshot).exists():
            try:
                content.append({"type": "input_text", "text": f"Evidence screenshot for event_id {step['event_id']}:"})
                content.append(
                    {
                        "type": "input_image",
                        "image_url": f"data:image/jpeg;base64,{_encode_image(screenshot)}",
                        "detail": "low",
                    }
                )
            except Exception:
                pass

    response = client.responses.create(
        model=model,
        input=[
            {
                "role": "user",
                "content": content,
            }
        ],
        temperature=0.1,
    )
    return _extract_json(getattr(response, "output_text", "") or "")


def verify_steps(steps: list[dict[str, Any]], model: str | None = None, max_risky: int = 24) -> list[dict[str, Any]]:
    marked = mark_risks(steps)
    risky = [step for step in marked if step.get("risky")]
    if not risky or not os.getenv("OPENAI_API_KEY"):
        return [
            {
                **step,
                "action": _sanitize_risky_text(step.get("action", "")) if step.get("risky") else step.get("action", ""),
                "expected_output": _sanitize_risky_text(step.get("expected_output", ""))
                if step.get("risky")
                else step.get("expected_output", ""),
                "confidence": "medium" if step.get("risky") and step.get("confidence") == "high" else step.get("confidence"),
            }
            for step in marked
        ]

    model = model or os.getenv("OPENAI_MODEL", "gpt-5.5")
    risky = risky[:max_risky]
    try:
        verified = _call_verify(risky, model)
    except Exception:
        time.sleep(1)
        try:
            verified = _call_verify(risky, model)
        except Exception:
            return [
                {
                    **step,
                    "action": _sanitize_risky_text(step.get("action", "")) if step.get("risky") else step.get("action", ""),
                    "expected_output": _sanitize_risky_text(step.get("expected_output", ""))
                    if step.get("risky")
                    else step.get("expected_output", ""),
                    "confidence": "medium" if step.get("risky") and step.get("confidence") == "high" else step.get("confidence"),
                }
                for step in marked
            ]

    updates = {int(item.get("event_id", -1)): item for item in verified if str(item.get("event_id", "")).isdigit()}
    out = []
    for step in marked:
        update = updates.get(int(step["event_id"]))
        if update:
            step = {
                **step,
                "system": update.get("system") or step["system"],
                "action": update.get("action") or step["action"],
                "expected_output": update.get("expected_output") or step["expected_output"],
                "confidence": update.get("confidence") if update.get("confidence") in {"high", "medium", "low"} else step["confidence"],
                "verified": True,
            }
        if step.get("risky"):
            step = {
                **step,
                "action": _sanitize_risky_text(step.get("action", "")),
                "expected_output": _sanitize_risky_text(step.get("expected_output", "")),
            }
        out.append(step)
    return out
