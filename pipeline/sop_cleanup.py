from __future__ import annotations

import re
from collections import Counter, OrderedDict
from typing import Any


MEANINGFUL_VERB_ROOTS = {
    "open",
    "select",
    "click",
    "create",
    "confirm",
    "enter",
    "type",
    "filter",
    "export",
    "save",
    "submit",
    "post",
    "approve",
    "reject",
    "reconcile",
    "upload",
    "download",
    "generate",
    "refresh",
    "insert",
    "add",
    "remove",
    "rename",
    "move",
    "reorder",
    "drag",
    "drop",
    "apply",
    "choose",
    "configure",
    "update",
    "delete",
    "format",
    "sort",
    "validate",
    "verify",
    "change",
    "start",
}

STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "be",
    "by",
    "for",
    "from",
    "in",
    "into",
    "is",
    "it",
    "of",
    "on",
    "or",
    "the",
    "that",
    "this",
    "to",
    "with",
    "within",
    "visible",
    "screen",
}

NOISE_PATTERNS = [
    r"\bpresenter\b.*\boutro\b",
    r"\boutro\b.*\bscreen\b",
    r"\bpresenter video\b",
    r"\bsocial media\b",
    r"\bfollow banner\b",
    r"\bsubscribe\b",
    r"\blike\b.*\bcomment\b",
    r"\byoutube\b.*\bend card\b",
    r"\bend card\b",
    r"\bintro\b.*\btitle\b",
    r"\btitle screen\b",
    r"\bscreen remains visible\b",
    r"\bpresenter outro remains visible\b",
]

PASSIVE_PATTERNS = [
    r"^review the worksheet data\b",
    r"^review the pivottable fields pane\b",
    r"^review the visible process screen\b",
    r"^review the screen\b",
    r"^review the visible .*screen\b",
    r"^review the presenter outro screen\b",
    r"^review the .*tab\b",
    r"^review the .*pane\b",
    r"^review the process screen\b",
    r"^the screen is visible\b",
    r"\bscreen remains visible\b",
]

VALIDATION_TERMS = {
    "validate",
    "verify",
    "confirm",
}

VALIDATION_OUTPUT_TERMS = {
    "appears",
    "available",
    "changed",
    "created",
    "displayed",
    "exported",
    "listed",
    "posted",
    "ready",
    "saved",
    "shows",
    "status",
    "updated",
}

GENERIC_PHASES = {"Process in Excel", "Validate"}
TIME_PATTERN = re.compile(r"(\d+(?:\.\d+)?)\s*s")
UNDER_COVERAGE_WARNING = "Possible under-coverage: many workflow events were not represented as SOP steps."


def _text(step: dict[str, Any]) -> str:
    return f"{step.get('action', '')} {step.get('expected_output', '')}".strip()


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", text.lower())).strip()


def _tokens(text: str) -> set[str]:
    return {token for token in _normalize(text).split() if token and token not in STOPWORDS}


def _jaccard(left: str, right: str) -> float:
    a = _tokens(left)
    b = _tokens(right)
    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0
    return len(a & b) / max(1, len(a | b))


def _verb_root(token: str) -> str:
    if token.endswith("ing") and len(token) > 5:
        token = token[:-3]
    if token.endswith("ed") and len(token) > 4:
        token = token[:-2]
    if token.endswith("s") and len(token) > 4:
        token = token[:-1]
    if token == "creat":
        return "create"
    return token


def _has_meaningful_action(step: dict[str, Any]) -> bool:
    action = str(step.get("action", "")).lower()
    tokens = re.findall(r"[a-z0-9]+", action)
    roots = {_verb_root(token) for token in tokens}
    if roots & MEANINGFUL_VERB_ROOTS:
        return True
    return bool(re.search(r"\bstart\s+creat", action))


def _is_noise(step: dict[str, Any]) -> bool:
    blob = _normalize(_text(step))
    if _has_meaningful_action(step) and not re.search(r"\bpresenter\b|\boutro\b|\bsocial\b|\byoutube\b|\bsubscribe\b", blob):
        return False
    return any(re.search(pattern, blob) for pattern in NOISE_PATTERNS)


def _is_validation_checkpoint(step: dict[str, Any]) -> bool:
    action = _normalize(str(step.get("action", "")))
    expected = _normalize(str(step.get("expected_output", "")))
    action_tokens = set(action.split())
    if not action_tokens & VALIDATION_TERMS:
        return False
    if "that" in action_tokens:
        return True
    return bool(set(expected.split()) & VALIDATION_OUTPUT_TERMS)


def _is_passive_review(step: dict[str, Any]) -> bool:
    action = _normalize(str(step.get("action", "")))
    expected = _normalize(str(step.get("expected_output", "")))
    passive = any(re.search(pattern, action) for pattern in PASSIVE_PATTERNS)
    passive = passive or bool(re.search(r"\bscreen is visible\b|\bscreen remains visible\b", expected))
    return passive and not _is_validation_checkpoint(step) and not _has_meaningful_action(step)


def _removed_record(step: dict[str, Any], reason: str) -> dict[str, Any]:
    return {
        "original_step_number": step.get("original_step_number") or step.get("step_number"),
        "action": step.get("action", ""),
        "expected_output": step.get("expected_output", ""),
        "reason": reason,
        "confidence": step.get("confidence", "medium"),
    }


def _sequence_number(step: dict[str, Any]) -> int:
    value = step.get("original_step_number") or step.get("step_number") or 0
    try:
        return int(value)
    except Exception:
        return 0


def _infer_seconds_from_text(value: Any) -> float | None:
    if not isinstance(value, str):
        return None
    match = TIME_PATTERN.search(value)
    if not match:
        return None
    try:
        return float(match.group(1))
    except Exception:
        return None


def _coerce_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except Exception:
        return _infer_seconds_from_text(value)


def _ordering_value(step: dict[str, Any]) -> tuple[int, float]:
    start = _coerce_float(step.get("start_time_seconds"))
    if start is None:
        start = _coerce_float(step.get("start_time_sec"))
    if start is None:
        start = _coerce_float(step.get("time_sec"))
    if start is not None:
        return (0, start)
    event = step.get("source_event_index")
    if event is None:
        event = step.get("event_id")
    try:
        return (1, float(event))
    except Exception:
        return (2, float(_sequence_number(step)))


def _normalize_ordering_metadata(step: dict[str, Any], fallback_number: int) -> dict[str, Any]:
    out = dict(step)
    out["original_step_number"] = out.get("original_step_number") or out.get("step_number") or fallback_number
    out["source_event_index"] = out.get("source_event_index") or out.get("event_id")
    start = _coerce_float(out.get("start_time_seconds"))
    if start is None:
        start = _coerce_float(out.get("start_time_sec"))
    if start is None:
        start = _coerce_float(out.get("time_sec"))
    if start is None:
        start = _infer_seconds_from_text(out.get("screenshot", ""))
    end = _coerce_float(out.get("end_time_seconds"))
    if end is None:
        end = _coerce_float(out.get("end_time_sec"))
    if end is None:
        end = start
    if start is not None:
        out["start_time_seconds"] = start
    if end is not None:
        out["end_time_seconds"] = end
    out["screen_state"] = out.get("screen_state") or out.get("screen_state_id")
    return out


def validate_chronological_order(steps: list[dict]) -> dict:
    violations = []
    previous_key: tuple[int, float] | None = None
    previous_step = None
    for step in steps:
        key = _ordering_value(step)
        if previous_key is not None and key < previous_key:
            violations.append(
                {
                    "previous_step_number": previous_step.get("step_number") if previous_step else None,
                    "current_step_number": step.get("step_number"),
                    "previous_order": previous_key,
                    "current_order": key,
                }
            )
        previous_key = key
        previous_step = step
    return {"is_chronological": not violations, "violations": violations}


def _time_distance(left: dict[str, Any], right: dict[str, Any]) -> float:
    left_time = left.get("end_time_seconds", left.get("end_time_sec", left.get("time_sec", 0))) or 0
    right_time = right.get("start_time_seconds", right.get("start_time_sec", right.get("time_sec", 0))) or 0
    try:
        return abs(float(right_time) - float(left_time))
    except Exception:
        return 0.0


def _same_workflow_intent(left: dict[str, Any], right: dict[str, Any]) -> bool:
    left_text = _normalize(_text(left))
    right_text = _normalize(_text(right))
    if "pivottable setup" in left_text and "create a new pivottable" in right_text:
        return True
    if "create a new pivottable" in left_text and "pivottable setup" in right_text:
        return True
    if "review the sales data table" in left_text and "review the worksheet data" in right_text:
        return True
    if "review the worksheet data" in left_text and "review the sales data table" in right_text:
        return True
    return _jaccard(_text(left), _text(right)) > 0.72


def _pivottable_setup_pair(left: dict[str, Any], right: dict[str, Any]) -> bool:
    left_text = _normalize(_text(left))
    right_text = _normalize(_text(right))
    return (
        "pivottable setup" in left_text
        and "create a new pivottable" in right_text
        or "create a new pivottable" in left_text
        and "pivottable setup" in right_text
    )


def _target_tokens(step: dict[str, Any]) -> set[str]:
    tokens = _tokens(_text(step))
    domain_terms = {
        "customer",
        "invoice",
        "order",
        "record",
        "report",
        "field",
        "status",
        "region",
        "salesperson",
        "amount",
        "pivottable",
        "pivotchart",
        "slicer",
        "table",
        "workbook",
        "document",
        "transaction",
        "posting",
    }
    return tokens & domain_terms


def _field_detail_tokens(step: dict[str, Any]) -> set[str]:
    tokens = _tokens(_text(step))
    detail_terms = {
        "status",
        "priority",
        "salesperson",
        "region",
        "amount",
        "percentage",
        "measure",
        "series",
        "slicer",
    }
    return (tokens & detail_terms) | {token for token in tokens if token.isdigit()}


def _distinct_pivot_field_operations(left: dict[str, Any], right: dict[str, Any]) -> bool:
    left_text = _normalize(str(left.get("action", "")))
    right_text = _normalize(str(right.get("action", "")))
    if not ("pivottable" in left_text or "pivottable" in right_text):
        return False
    field_terms = {"salesperson", "sales amount", "region", "column", "row", "value", "measure"}
    left_fields = {term for term in field_terms if term in left_text}
    right_fields = {term for term in field_terms if term in right_text}
    return bool(left_fields and right_fields and left_fields != right_fields)


def _action_roots(step: dict[str, Any]) -> set[str]:
    return {_verb_root(token) for token in re.findall(r"[a-z0-9]+", str(step.get("action", "")).lower())}


def _is_duplicate_candidate(left: dict[str, Any], right: dict[str, Any]) -> bool:
    if left.get("system", "Other") != right.get("system", "Other"):
        return False
    if _distinct_pivot_field_operations(left, right):
        return False
    number_gap = abs(_sequence_number(right) - _sequence_number(left))
    close_in_sequence = number_gap <= 2
    close_in_time = _time_distance(left, right) <= 45
    if not (close_in_sequence or close_in_time):
        return False
    left_targets = _target_tokens(left)
    right_targets = _target_tokens(right)
    if left_targets and right_targets and not (left_targets & right_targets):
        return False
    left_details = _field_detail_tokens(left)
    right_details = _field_detail_tokens(right)
    if left_details and right_details and left_details != right_details:
        return False
    left_roots = _action_roots(left) & MEANINGFUL_VERB_ROOTS
    right_roots = _action_roots(right) & MEANINGFUL_VERB_ROOTS
    same_intent = _same_workflow_intent(left, right)
    action_similarity = _jaccard(str(left.get("action", "")), str(right.get("action", "")))
    if left_roots and right_roots and left_roots != right_roots and action_similarity < 0.72 and not _pivottable_setup_pair(left, right):
        return False
    expected_overlap = _jaccard(str(left.get("expected_output", "")), str(right.get("expected_output", ""))) > 0.45
    return same_intent or expected_overlap and _jaccard(_text(left), _text(right)) > 0.55


def _specificity_score(step: dict[str, Any]) -> int:
    score = len(_tokens(_text(step)))
    if _has_meaningful_action(step):
        score += 8
    if _is_passive_review(step):
        score -= 5
    if _is_validation_checkpoint(step):
        score += 4
    return score


def _merge_pair(left: dict[str, Any], right: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    left_text = _normalize(_text(left))
    right_text = _normalize(_text(right))
    if "pivottable setup" in left_text and "create a new pivottable" in right_text:
        merged_action = "Confirm the PivotTable setup and open the blank PivotTable worksheet."
        merged_expected = right.get("expected_output") or left.get("expected_output") or "The blank PivotTable worksheet is ready."
        base = dict(right)
    elif _specificity_score(left) >= _specificity_score(right):
        merged_action = left.get("action", "")
        merged_expected = left.get("expected_output", "")
        base = dict(left)
    else:
        merged_action = right.get("action", "")
        merged_expected = right.get("expected_output", "")
        base = dict(right)

    source_numbers = [
        left.get("original_step_number") or left.get("step_number"),
        right.get("original_step_number") or right.get("step_number"),
    ]
    base.update(
        {
            "action": merged_action,
            "expected_output": merged_expected,
            "original_step_numbers": source_numbers,
            "cleanup_merged": True,
        }
    )
    record = {
        "source_step_numbers": source_numbers,
        "merged_action": merged_action,
        "merged_expected_output": merged_expected,
        "reason": "Adjacent duplicate or same-intent step merged conservatively.",
        "confidence": base.get("confidence", "medium"),
    }
    return base, record


def _workflow_family(steps: list[dict[str, Any]]) -> str:
    combined = " ".join(_normalize(_text(step) + " " + str(step.get("ocr", ""))) for step in steps)
    systems = Counter(step.get("system", "Other") for step in steps)
    if any(term in combined for term in ["pivottable", "pivot table", "pivotchart", "slicer"]):
        return "excel_pivottable"
    if systems.get("Excel"):
        return "excel"
    if systems.get("SAP"):
        return "sap"
    if systems.get("Browser"):
        return "browser_crud"
    return "generic"


def _is_review_style(step: dict[str, Any]) -> bool:
    action = _normalize(str(step.get("action", "")))
    return (
        action.startswith("review ")
        or action.startswith("validate ")
        or action.startswith("verify ")
        or action.startswith("confirm that ")
    )


def _review_object_terms(text: str) -> set[str]:
    found = set()
    for label, phrases in {
        "table": ["table", "worksheet", "source data", "header row"],
        "pivottable": ["pivottable", "pivot table"],
        "chart": ["pivotchart", "pivot chart", "chart"],
        "slicer": ["slicer"],
        "filter": ["filter"],
        "result": ["summary", "total", "result", "confirmation", "status", "message", "output", "export"],
    }.items():
        if any(phrase in text for phrase in phrases):
            found.add(label)
    return found


def _review_category(
    step: dict[str, Any],
    previous: dict[str, Any] | None,
    following: dict[str, Any] | None,
    workflow_family: str,
) -> str | None:
    if not (_is_review_style(step) or _is_passive_review(step) or _is_validation_checkpoint(step)):
        return None
    if _is_validation_checkpoint(step):
        return "operational_checkpoint"

    text = _normalize(_text(step))
    object_terms = _review_object_terms(text)
    previous_meaningful = bool(previous and _has_meaningful_action(previous))
    next_meaningful = bool(following and _has_meaningful_action(following))
    bridges_transition = bool(
        previous_meaningful
        and next_meaningful
        and (
            previous.get("system") != following.get("system")
            or _target_tokens(previous) != _target_tokens(following)
            or _action_roots(previous) != _action_roots(following)
        )
    )

    if workflow_family.startswith("excel"):
        if any(
            term in text
            for term in [
                "worksheet data",
                "fields pane",
                "design tab",
                "visible process screen",
                "screen remains visible",
            ]
        ):
            return "passive_filler"
        verifies_output = any(
            term in text
            for term in [
                "formatted excel table",
                "selected header row",
                "source data table",
                "pivottable summary",
                "pivot table summary",
                "pivottable with",
                "pivot table with",
                "pivotchart",
                "pivot chart",
                "slicer",
                "filter",
                "percentage column",
            ]
        )
        if verifies_output and previous_meaningful:
            return "operational_checkpoint"
        if verifies_output and (next_meaningful or bridges_transition):
            return "contextual_review"
    if object_terms and previous_meaningful:
        return "operational_checkpoint"
    if object_terms and (next_meaningful or bridges_transition):
        return "contextual_review"
    return "passive_filler"


def _phase_for_step(step: dict[str, Any], workflow_family: str) -> str:
    text = _normalize(_text(step))
    if workflow_family == "sap":
        if any(term in text for term in ["save", "post", "submit"]):
            return "Save or post document"
        if any(term in text for term in ["validate", "verify", "confirm", "check", "status"]):
            return "Validate posting"
        if any(term in text for term in ["enter", "document", "invoice", "field", "data", "vendor", "amount"]):
            return "Enter document data"
        return "Open transaction"
    if workflow_family == "browser_crud":
        if any(term in text for term in ["export", "download", "report", "close"]):
            return "Export, save, or close process"
        if any(term in text for term in ["validate", "verify", "confirm", "appears", "confirmation", "status changed"]):
            return "Validate result"
        if any(term in text for term in ["submit", "save", "apply"]):
            return "Submit changes"
        if any(term in text for term in ["update", "enter", "field", "edit", "change", "rename"]):
            return "Update fields"
        return "Navigate to record"
    if workflow_family == "excel_pivottable":
        if any(term in text for term in ["pivotchart", "pivot chart", "chart", "slicer"]):
            if any(term in text for term in ["apply", "review", "validate", "verify", "confirm"]):
                return "Validate final output"
            return "Build chart and slicer"
        if any(term in text for term in ["percentage", "measure", "rename", "format", "calculation", "sum", "maximum", "max"]):
            return "Add calculations and formatting"
        if any(term in text for term in ["row field", "column field", "value field", "salesperson", "region", "rows area", "columns area", "move region", "reorder row"]):
            return "Configure PivotTable fields"
        if "pivottable" in text and any(term in text for term in ["create", "setup", "worksheet", "table"]):
            return "Create PivotTable"
        if "table" in text and "pivottable" not in text and any(term in text for term in ["create", "confirm", "formatted", "selected range", "headers"]):
            return "Create Excel table"
        if any(term in text for term in ["validate", "verify", "summary", "totals", "result", "final output"]):
            return "Validate final output"
        return "Prepare source data"
    if workflow_family == "excel":
        if any(term in text for term in ["export", "download", "save", "close"]):
            return "Export, save, or close process"
        if any(term in text for term in ["validate", "verify", "confirm", "summary", "result"]):
            return "Review and validate"
        if any(term in text for term in ["format", "formula", "calculation", "chart", "table", "pivot"]):
            return "Configure records or fields"
        if any(term in text for term in ["select", "prepare", "enter", "input", "source data", "worksheet"]):
            return "Prepare input data"
        return "Open or access process"
    if any(term in text for term in ["export", "download", "generate", "close"]):
        return "Export, save, or close process"
    if any(term in text for term in ["validate", "verify", "review", "confirm", "check", "status"]):
        return "Review and validate"
    if any(term in text for term in ["submit", "post", "approve", "reject", "execute", "save"]):
        return "Execute main action"
    if any(term in text for term in ["configure", "setting", "filter", "choose", "apply", "field", "update", "change"]):
        return "Configure records or fields"
    if any(term in text for term in ["prepare", "select", "enter", "upload", "input"]):
        return "Prepare input data"
    return "Open or access process"


def _correct_phase_for_intent(step: dict[str, Any], phase: str, workflow_family: str) -> tuple[str, bool]:
    text = _normalize(_text(step))
    corrected = phase
    if workflow_family == "excel_pivottable":
        if "slicer" in text and any(term in text for term in ["apply", "review", "validate", "verify"]):
            corrected = "Validate final output"
        elif any(term in text for term in ["pivotchart", "pivot chart", "insert a pivotchart", "insert pivotchart"]):
            corrected = "Build chart and slicer"
        elif any(term in text for term in ["insert slicers", "insert slicer", "region slicer", "open the insert slicers dialog"]):
            corrected = "Build chart and slicer"
        elif any(term in text for term in ["percentage", "measure", "rename", "sum", "maximum", "max"]):
            corrected = "Add calculations and formatting"
        elif any(term in text for term in ["review the pivottable summary", "review the pivottable", "review the pivot table", "review the pivotchart and slicer"]):
            corrected = "Validate final output"
    return corrected, corrected != phase


def _apply_phases(steps: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    workflow_family = _workflow_family(steps)
    phase_counts: OrderedDict[str, int] = OrderedDict()
    timeline_sections = []
    current_phase = None
    phased = []
    corrections = 0
    for step in steps:
        phase = _phase_for_step(step, workflow_family)
        phase, corrected = _correct_phase_for_intent(step, phase, workflow_family)
        corrections += int(corrected)
        phase_counts[phase] = phase_counts.get(phase, 0) + 1
        if phase != current_phase:
            timeline_sections.append({"phase": phase, "start_step_number": step.get("step_number")})
            current_phase = phase
        phased.append({**step, "phase": phase})
    return phased, {
        "phase_counts": dict(phase_counts),
        "phase_order": [section["phase"] for section in timeline_sections],
        "timeline_sections": timeline_sections,
        "workflow_type": workflow_family,
        "phase_corrections": corrections,
    }


def _renumber(steps: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [{**step, "step_number": index + 1} for index, step in enumerate(steps)]


def _remaining_counts(steps: list[dict[str, Any]]) -> tuple[int, int, int]:
    noise = sum(1 for step in steps if _is_noise(step))
    passive = sum(1 for step in steps if step.get("review_category") == "contextual_review" or _is_passive_review(step))
    duplicates = sum(1 for left, right in zip(steps, steps[1:]) if _is_duplicate_candidate(left, right))
    return noise, passive, duplicates


def _coverage_minimum(event_segments: int) -> int:
    if event_segments >= 35:
        return 24
    if event_segments >= 30:
        return 22
    if event_segments >= 25:
        return 18
    return 0


def _event_segments_from_metadata(metadata: dict[str, Any] | None) -> int:
    if not metadata:
        return 0
    for key in ("event_segments", "events"):
        value = metadata.get(key)
        try:
            if value is not None:
                return int(value)
        except Exception:
            pass
    segmentation = metadata.get("segmentation") or {}
    try:
        return int(segmentation.get("event_segments") or 0)
    except Exception:
        return 0


def _coverage_justification(metadata: dict[str, Any] | None) -> str:
    if not metadata:
        return ""
    return str(metadata.get("coverage_justification") or "").strip()


def _suspicious_review_runs(steps: list[dict[str, Any]]) -> list[dict[str, Any]]:
    runs: list[dict[str, Any]] = []
    start = None
    for index, step in enumerate(steps):
        is_review_run_step = step.get("review_category") in {"contextual_review", "passive_filler"} or (
            _is_review_style(step) and not _has_meaningful_action(step)
        )
        if is_review_run_step:
            start = index if start is None else start
            continue
        if start is not None and index - start >= 2:
            runs.append(
                {
                    "start_step_number": steps[start].get("step_number"),
                    "end_step_number": steps[index - 1].get("step_number"),
                    "count": index - start,
                }
            )
        start = None
    if start is not None and len(steps) - start >= 2:
        runs.append(
            {
                "start_step_number": steps[start].get("step_number"),
                "end_step_number": steps[-1].get("step_number"),
                "count": len(steps) - start,
            }
        )
    return runs


def _completeness_signals(steps: list[dict[str, Any]], event_segments: int) -> dict[str, Any]:
    workflow_family = _workflow_family(steps)
    warnings: list[str] = []
    missing_action_patterns: list[str] = []
    suspicious_review_runs = _suspicious_review_runs(steps)

    if suspicious_review_runs:
        warnings.append("Long review-only runs remain and may indicate missing operational actions.")

    operational_steps = [step for step in steps if _has_meaningful_action(step)]
    if event_segments >= 25 and len(operational_steps) < max(12, int(len(steps) * 0.55)):
        warnings.append("Operational action density is low relative to the number of detected workflow events.")

    if event_segments >= 25:
        previous_operational_event = None
        for step in operational_steps:
            event_index = step.get("source_event_index")
            try:
                event_number = int(event_index)
            except Exception:
                event_number = None
            if previous_operational_event is not None and event_number is not None and event_number - previous_operational_event >= 5:
                warnings.append("Some event-rich sections are represented by very few operational steps.")
                break
            if event_number is not None:
                previous_operational_event = event_number

    combined_text = " ".join(
        _normalize(
            f"{step.get('action', '')} {step.get('expected_output', '')} {step.get('ocr', '')}"
        )
        for step in steps
    )
    actions_text = " ".join(_normalize(step.get("action", "")) for step in steps)
    if workflow_family == "excel_pivottable":
        if "percentage" in combined_text and "rename the percentage" in actions_text:
            if not any(
                phrase in actions_text
                for phrase in [
                    "add a second sales amount measure",
                    "display it as a percentage",
                    "show values as a percentage",
                ]
            ):
                missing_action_patterns.append("Percentage measure configuration may be under-described.")
        if "slicer" in combined_text and "apply the region slicer" not in actions_text and "apply the slicer" not in actions_text:
            missing_action_patterns.append("Slicer application appears in the evidence but is not described operationally.")
        if "pivotchart" in combined_text and "insert a pivotchart" not in actions_text and "insert pivotchart" not in actions_text:
            missing_action_patterns.append("PivotChart creation appears in the evidence but is not described clearly.")
    return {
        "coverage_warnings": warnings,
        "missing_action_patterns": missing_action_patterns,
        "suspicious_review_runs": suspicious_review_runs,
        "workflow_family": workflow_family,
    }


def _semantic_counts(steps: list[dict[str, Any]]) -> dict[str, Any]:
    source_counts = Counter(str(step.get("generation_source") or "unknown") for step in steps)
    diagnostic_count = sum(1 for step in steps if step.get("diagnostic_only") or step.get("generation_source") == "diagnostic_fallback")
    generic_review_count = sum(
        1
        for step in steps
        if _is_review_style(step)
        and not _has_meaningful_action(step)
        or str(step.get("action", "")).lower().startswith("review the process state shown")
    )
    operational_action_count = sum(1 for step in steps if _has_meaningful_action(step) and not step.get("diagnostic_only"))
    semantic_coverage_score = round(operational_action_count / max(1, len(steps)), 3)
    return {
        "generation_source_counts": dict(source_counts),
        "diagnostic_step_count": diagnostic_count,
        "generic_review_count": generic_review_count,
        "operational_action_count": operational_action_count,
        "semantic_coverage_score": semantic_coverage_score,
    }


def _quality_report(
    before_count: int,
    steps: list[dict[str, Any]],
    removed_steps: list[dict[str, Any]],
    merged_steps: list[dict[str, Any]],
    warnings: list[str],
    chronological_report: dict[str, Any],
    chronology_repaired: bool,
    event_segments: int,
    coverage_justification: str,
    completeness: dict[str, Any],
    phase_summary: dict[str, Any],
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    metadata = metadata or {}
    noise_count, passive_count, duplicate_count = _remaining_counts(steps)
    semantic = _semantic_counts(steps)
    low_confidence_count = sum(1 for step in steps if step.get("confidence") != "high")
    operational_checkpoint_count = sum(1 for step in steps if step.get("review_category") == "operational_checkpoint")
    contextual_review_count = sum(1 for step in steps if step.get("review_category") == "contextual_review")
    passive_filler_removed_count = sum(
        1 for item in removed_steps if "passive" in str(item.get("reason", "")).lower() or "duplicated passive" in str(item.get("reason", "")).lower()
    )
    generic_phase_count = sum(1 for step in steps if step.get("phase") in GENERIC_PHASES)
    coverage_ratio_before = round(before_count / event_segments, 3) if event_segments else None
    coverage_ratio_after = round(len(steps) / event_segments, 3) if event_segments else None
    coverage_minimum = _coverage_minimum(event_segments)
    raw_under_coverage = bool(event_segments and coverage_minimum and before_count < coverage_minimum)
    medium_or_long = event_segments >= 25
    final_under_coverage = bool(event_segments and coverage_ratio_after is not None and coverage_ratio_after < 0.60)
    medium_long_coverage_shortfall = bool(medium_or_long and coverage_ratio_after is not None and coverage_ratio_after < 0.70)
    coverage_guardrail_triggered = raw_under_coverage or final_under_coverage
    score = 100
    score -= 10 * noise_count
    score -= 5 * duplicate_count
    score -= 3 * max(0, passive_count - 2)
    score -= 2 * low_confidence_count
    if raw_under_coverage:
        score -= 30
    if final_under_coverage:
        score -= 35
    if medium_long_coverage_shortfall:
        score -= 15
    if semantic["diagnostic_step_count"]:
        score -= min(60, 8 * semantic["diagnostic_step_count"])
    if event_segments >= 25 and semantic["semantic_coverage_score"] < 0.55:
        score -= 35
    if steps and semantic["generic_review_count"] / len(steps) > 0.20:
        score -= 25
    score -= 8 * len(completeness.get("missing_action_patterns", []))
    score -= 5 * len(completeness.get("suspicious_review_runs", []))
    if not steps:
        score = 0
    elif len(steps) < 8:
        score -= 10
    if steps and low_confidence_count / len(steps) > 0.25:
        score -= 10
    chronological_valid = chronological_report.get("is_chronological", True)
    chronological_violations_count = len(chronological_report.get("violations", []))
    if chronological_violations_count:
        score -= 20
    phase_names = {step.get("phase") for step in steps if step.get("phase")}
    if len(phase_names) == 1 and next(iter(phase_names), "") in GENERIC_PHASES:
        score -= 5
    if generic_phase_count == len(steps) and steps:
        score -= 5
    score = max(0, min(100, score))
    coverage_blocks_demo = coverage_guardrail_triggered and not coverage_justification
    readiness_blockers: list[str] = []
    generation_mode = str(metadata.get("generation_mode") or "unknown")
    ocr_available = bool(metadata.get("ocr_available"))
    ocr_non_empty_count = int(metadata.get("ocr_non_empty_count") or 0)
    openai_configured = bool(metadata.get("openai_configured"))
    openai_calls_attempted = int(metadata.get("openai_calls_attempted") or 0)
    openai_calls_succeeded = int(metadata.get("openai_calls_succeeded") or 0)
    openai_errors = list(metadata.get("openai_errors") or [])
    has_capability_metadata = any(
        key in metadata
        for key in (
            "generation_mode",
            "openai_configured",
            "ocr_available",
            "ocr_non_empty_count",
        )
    )
    if not (chronological_valid or chronology_repaired):
        readiness_blockers.append("Chronological order remains inconsistent.")
    if noise_count:
        readiness_blockers.append("Obvious non-operational video noise remains in the SOP.")
    if medium_long_coverage_shortfall:
        readiness_blockers.append("Coverage is too low for a medium or long workflow recording.")
    if coverage_blocks_demo:
        readiness_blockers.append(UNDER_COVERAGE_WARNING)
    if contextual_review_count > max(3, len(steps) // 5):
        readiness_blockers.append("Too many passive review steps remain relative to operational actions.")
    if generation_mode == "diagnostic_only":
        readiness_blockers.append("Diagnostic draft mode was used because no production evidence source was available.")
    if semantic["diagnostic_step_count"] > len(steps) / 2:
        readiness_blockers.append("Most steps came from diagnostic fallback generation.")
    if has_capability_metadata and not openai_configured and not ocr_non_empty_count:
        readiness_blockers.append("OpenAI vision was unavailable and OCR produced no usable text.")
    if openai_configured and openai_calls_attempted and openai_calls_succeeded == 0:
        readiness_blockers.append("OpenAI vision generation was attempted but did not succeed.")
    if event_segments >= 25 and semantic["semantic_coverage_score"] < 0.55:
        readiness_blockers.append("Operational action coverage is too low for a medium or long workflow.")
    if steps and semantic["generic_review_count"] / len(steps) > 0.20:
        readiness_blockers.append("Too many generic review rows remain.")
    if completeness.get("missing_action_patterns"):
        readiness_blockers.extend(completeness["missing_action_patterns"])
    if phase_summary.get("phase_corrections", 0) >= 3:
        warnings.append("Multiple phase labels were corrected to match action intent.")

    coverage_gate = not medium_long_coverage_shortfall and not coverage_blocks_demo and not raw_under_coverage
    operational_gate = not noise_count and (chronological_valid or chronology_repaired) and not completeness.get("missing_action_patterns")
    passive_gate = contextual_review_count <= max(3, len(steps) // 5)
    semantic_gate = not readiness_blockers and semantic["diagnostic_step_count"] == 0

    if score >= 80 and coverage_gate and operational_gate and passive_gate and semantic_gate:
        readiness = "demo_ready"
    elif score >= 60:
        readiness = "needs_review"
    else:
        readiness = "not_ready"
    return {
        "step_count_before": before_count,
        "step_count_after": len(steps),
        "removed_count": len(removed_steps),
        "merged_count": len(merged_steps),
        "low_confidence_count": low_confidence_count,
        "passive_step_count": passive_count,
        "noise_step_count": noise_count,
        "duplicate_candidate_count": duplicate_count,
        "chronological_order_valid": chronological_valid or chronology_repaired,
        "chronological_violations_count": chronological_violations_count,
        "event_segments": event_segments,
        "coverage_ratio_before_cleanup": coverage_ratio_before,
        "coverage_ratio_after_cleanup": coverage_ratio_after,
        "coverage_guardrail_triggered": coverage_guardrail_triggered,
        "coverage_justification": coverage_justification,
        "operational_checkpoint_count": operational_checkpoint_count,
        "contextual_review_count": contextual_review_count,
        "passive_filler_removed_count": passive_filler_removed_count,
        "coverage_warnings": completeness.get("coverage_warnings", []),
        "missing_action_patterns": completeness.get("missing_action_patterns", []),
        "suspicious_review_runs": completeness.get("suspicious_review_runs", []),
        "generation_mode": generation_mode,
        "generation_source_counts": semantic["generation_source_counts"],
        "openai_configured": openai_configured,
        "openai_calls_attempted": openai_calls_attempted,
        "openai_calls_succeeded": openai_calls_succeeded,
        "openai_errors": openai_errors,
        "ocr_available": ocr_available,
        "ocr_non_empty_count": ocr_non_empty_count,
        "semantic_coverage_score": semantic["semantic_coverage_score"],
        "operational_action_count": semantic["operational_action_count"],
        "generic_review_count": semantic["generic_review_count"],
        "diagnostic_step_count": semantic["diagnostic_step_count"],
        "semantic_coverage_warnings": completeness.get("coverage_warnings", []),
        "readiness_blockers": readiness_blockers,
        "quality_score": score,
        "readiness": readiness,
        "warnings": warnings,
    }


def clean_sop_steps(
    steps: list[dict],
    metadata: dict | None = None,
    max_steps: int | None = None,
) -> dict:
    original = [_normalize_ordering_metadata(step, index + 1) for index, step in enumerate(steps)]
    event_segments = _event_segments_from_metadata(metadata)
    coverage_justification = _coverage_justification(metadata)
    coverage_minimum = _coverage_minimum(event_segments)
    raw_under_coverage = bool(event_segments and coverage_minimum and len(original) < coverage_minimum)
    workflow_family = _workflow_family(original)
    initial_chronology = validate_chronological_order(original)
    if not initial_chronology["is_chronological"]:
        original = sorted(original, key=_ordering_value)
    chronology_repaired = not initial_chronology["is_chronological"]
    hard_removed: list[dict[str, Any]] = []
    borderline_removed: list[dict[str, Any]] = []
    kept: list[dict[str, Any]] = []
    seen_passive_signatures: Counter[str] = Counter()

    for index, step in enumerate(original):
        signature = _normalize(_text(step))
        previous = original[index - 1] if index > 0 else None
        following = original[index + 1] if index + 1 < len(original) else None
        review_category = _review_category(step, previous, following, workflow_family)
        if _is_noise(step):
            hard_removed.append(_removed_record(step, "Removed obvious non-operational presenter/outro/social noise."))
            continue
        if review_category == "passive_filler":
            reason = "Removed passive review-only step without validation value."
            if signature in seen_passive_signatures:
                reason = "Removed duplicated passive observation."
            borderline_removed.append(_removed_record(step, reason))
            seen_passive_signatures[signature] += 1
            continue
        kept.append({**step, "review_category": review_category})

    candidate_removed = hard_removed + borderline_removed
    reduction_ratio = len(candidate_removed) / max(1, len(original))
    warnings: list[str] = []
    if chronology_repaired:
        warnings.append("Chronological order was repaired before cleanup.")
    projected_after_removal = len(original) - len(candidate_removed)
    cleanup_would_under_cover = bool(event_segments >= 25 and projected_after_removal / event_segments < 0.60)
    if raw_under_coverage or cleanup_would_under_cover:
        warnings.append(UNDER_COVERAGE_WARNING)
        if not coverage_justification:
            warnings.append("Cleanup stayed conservative because removing borderline steps would leave too little event coverage.")
        kept = []
        removed_steps = hard_removed
        hard_removed_numbers = {item["original_step_number"] for item in hard_removed}
        for step in original:
            number = step.get("original_step_number")
            if number not in hard_removed_numbers:
                kept.append({**step, "review_category": _review_category(step, None, None, workflow_family)})
    elif reduction_ratio > 0.40 and len(original) >= 5:
        warnings.append("Cleanup was conservative because too many steps were at risk of removal.")
        kept = []
        removed_steps = hard_removed
        hard_removed_numbers = {item["original_step_number"] for item in hard_removed}
        for step in original:
            number = step.get("original_step_number")
            if number not in hard_removed_numbers:
                kept.append({**step, "review_category": _review_category(step, None, None, workflow_family)})
    else:
        removed_steps = candidate_removed

    merged_records: list[dict[str, Any]] = []
    merged: list[dict[str, Any]] = []
    index = 0
    while index < len(kept):
        current = kept[index]
        if index + 1 < len(kept) and _is_duplicate_candidate(current, kept[index + 1]):
            merged_step, record = _merge_pair(current, kept[index + 1])
            merged.append(merged_step)
            merged_records.append(record)
            index += 2
            continue
        merged.append(current)
        index += 1

    if coverage_minimum and len(merged) < coverage_minimum <= len(kept):
        warnings.append("Cleanup skipped borderline merging because it would leave too little event coverage.")
        merged = kept
        merged_records = []

    if max_steps is not None:
        merged = merged[:max_steps]

    ordered = sorted(merged, key=_ordering_value)
    if event_segments and ordered and len(ordered) / event_segments < 0.60 and UNDER_COVERAGE_WARNING not in warnings:
        warnings.append(UNDER_COVERAGE_WARNING)
    final_chronology = validate_chronological_order(ordered)
    if not final_chronology["is_chronological"]:
        warnings.append("Chronological order required final repair.")
        ordered = sorted(ordered, key=_ordering_value)
    phased, phase_summary = _apply_phases(_renumber(ordered))
    repaired_chronology = validate_chronological_order(phased)
    completeness = _completeness_signals(phased, event_segments)
    for coverage_warning in completeness.get("coverage_warnings", []):
        if coverage_warning not in warnings:
            warnings.append(coverage_warning)
    quality_report = _quality_report(
        len(original),
        phased,
        removed_steps,
        merged_records,
        warnings,
        initial_chronology,
        chronology_repaired or final_chronology["violations"] != [],
        event_segments,
        coverage_justification,
        completeness,
        phase_summary,
        metadata,
    )
    quality_report["chronological_order_valid"] = repaired_chronology["is_chronological"]
    return {
        "steps": phased,
        "removed_steps": removed_steps,
        "merged_steps": merged_records,
        "phase_summary": phase_summary,
        "quality_report": quality_report,
    }
