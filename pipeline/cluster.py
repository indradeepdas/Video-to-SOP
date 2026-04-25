from __future__ import annotations

import hashlib
import re
from typing import Any


BUSINESS_ACTION_TERMS = [
    "open",
    "display",
    "filter",
    "export",
    "save",
    "post",
    "enter",
    "select",
    "search",
    "validate",
    "approve",
    "invoice",
    "supplier",
    "vendor",
    "payment",
    "purchase",
    "order",
    "amount",
    "date",
]

ACTION_HINTS = [
    ("filter", ["filter", "criteria", "date range", "status"]),
    ("export", ["export", "download", "xlsx", "spreadsheet", "csv"]),
    ("data entry", ["enter", "type", "field", "required", "value"]),
    ("review", ["review", "validate", "check", "confirm", "reconcile"]),
    ("post/save", ["post", "save", "submit", "approve"]),
    ("navigation", ["open", "display", "search", "select", "transaction"]),
]


def _tokens(text: str) -> set[str]:
    return {token for token in re.findall(r"[a-z0-9]{3,}", text.lower()) if len(token) >= 3}


def _similarity(left: str, right: str) -> float:
    a = _tokens(left)
    b = _tokens(right)
    if not a or not b:
        return 0.0
    return len(a & b) / max(1, len(a | b))


def _signature(event: dict[str, Any]) -> str:
    text = (event.get("clean_text") or event.get("raw_text") or "")[:500].lower()
    system = event.get("system", "Other")
    return hashlib.sha1(f"{system}:{text}".encode("utf-8", errors="ignore")).hexdigest()[:12]


def _action_hint(text: str) -> str:
    lower = text.lower()
    scores = [(name, sum(term in lower for term in terms)) for name, terms in ACTION_HINTS]
    best_name, best_score = max(scores, key=lambda item: item[1])
    return best_name if best_score > 0 else "review"


def _add_context(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    contextual = []
    for index, event in enumerate(events):
        before = events[index - 1] if index > 0 else event
        after = events[index + 1] if index < len(events) - 1 else event
        text = event.get("clean_text") or event.get("raw_text") or ""
        contextual.append(
            {
                **event,
                "event_id": index + 1,
                "before_frame": before.get("path"),
                "evidence_frame": event.get("path"),
                "after_frame": after.get("path"),
                "start_time_sec": before.get("time_sec", event.get("time_sec", 0)),
                "end_time_sec": after.get("time_sec", event.get("time_sec", 0)),
                "action_hint": _action_hint(text),
            }
        )
    return contextual


def cluster_events(events: list[dict[str, Any]], target_max: int = 60) -> list[dict[str, Any]]:
    if not events:
        return []

    clustered: list[dict[str, Any]] = []
    previous: dict[str, Any] | None = None
    for event in events:
        text = event.get("clean_text", "")
        if previous:
            same_system = event.get("system") == previous.get("system")
            similar = _similarity(text, previous.get("clean_text", "")) > 0.82
            low_change = float(event.get("diff_score", 0)) < 0.025
            system_transition = previous and event.get("system") != previous.get("system")
            if same_system and not system_transition and (similar or (low_change and not text)):
                if len(text) > len(previous.get("clean_text", "")):
                    previous.update(event)
                continue
        item = {**event, "event_id": len(clustered) + 1, "signature": _signature(event)}
        clustered.append(item)
        previous = item

    if len(clustered) <= target_max:
        return _add_context(clustered)

    high_change = sorted(clustered, key=lambda item: item.get("diff_score", 0), reverse=True)
    keep_ids = {clustered[0]["event_id"], clustered[-1]["event_id"]}
    keep_ids.update(item["event_id"] for item in high_change[: target_max - 2])
    return _add_context([event for event in clustered if event["event_id"] in keep_ids])


def prune_events(events: list[dict[str, Any]], max_events: int = 40) -> list[dict[str, Any]]:
    scored = []
    seen_signatures = set()
    for event in events:
        text = (event.get("clean_text") or "").lower()
        signature = event.get("signature") or _signature(event)
        if signature in seen_signatures:
            continue
        seen_signatures.add(signature)

        action_score = sum(term in text for term in BUSINESS_ACTION_TERMS)
        change_score = min(4.0, float(event.get("diff_score", 0)) * 60)
        system_score = 1.0 if event.get("system") != "Other" else 0.0
        text_score = min(3.0, len(text) / 180.0)
        transition_score = 2.0 if scored and event.get("system") != scored[-1][1].get("system") else 0.0
        hint_score = 1.5 if event.get("action_hint") in {"filter", "export", "data entry", "post/save"} else 0.0
        score = action_score + change_score + system_score + text_score + transition_score + hint_score

        toolbar_only = len(_tokens(text)) <= 4 and action_score == 0 and event.get("system") == "Other"
        if toolbar_only and event not in (events[0], events[-1]):
            continue
        scroll_only = float(event.get("diff_score", 0)) < 0.018 and _similarity(text, scored[-1][1].get("clean_text", "")) > 0.7 if scored else False
        if scroll_only and event.get("system") == scored[-1][1].get("system"):
            continue
        scored.append((score, event))

    if len(scored) <= max_events:
        chosen = [event for _, event in scored]
    else:
        anchors = [events[0], events[-1]]
        chosen_ids = {id(item) for item in anchors}
        ranked = sorted(scored, key=lambda item: item[0], reverse=True)
        for _, event in ranked:
            chosen_ids.add(id(event))
            if len(chosen_ids) >= max_events:
                break
        chosen = [event for _, event in scored if id(event) in chosen_ids]

    return _add_context(chosen[:max_events])
