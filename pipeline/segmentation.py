from __future__ import annotations

import base64
import json
import math
import os
import re
import time
from pathlib import Path
from statistics import median
from typing import Any

import cv2
import numpy as np

from pipeline.classify import classify_system
from pipeline.clean_ocr import clean_text
from pipeline.cluster import _action_hint, _similarity
from pipeline.ocr import run_ocr
from pipeline.video import _hash_distance


def _read_gray(path: str, size: tuple[int, int] = (220, 124)) -> np.ndarray | None:
    image = cv2.imread(path)
    if image is None:
        return None
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    return cv2.resize(gray, size, interpolation=cv2.INTER_AREA)


def _ssim_score(left: np.ndarray, right: np.ndarray) -> float:
    left_f = left.astype(np.float64)
    right_f = right.astype(np.float64)
    c1 = 6.5025
    c2 = 58.5225
    kernel = (7, 7)
    mu_left = cv2.GaussianBlur(left_f, kernel, 1.5)
    mu_right = cv2.GaussianBlur(right_f, kernel, 1.5)
    sigma_left = cv2.GaussianBlur(left_f * left_f, kernel, 1.5) - mu_left * mu_left
    sigma_right = cv2.GaussianBlur(right_f * right_f, kernel, 1.5) - mu_right * mu_right
    sigma_both = cv2.GaussianBlur(left_f * right_f, kernel, 1.5) - mu_left * mu_right
    numerator = (2 * mu_left * mu_right + c1) * (2 * sigma_both + c2)
    denominator = (mu_left * mu_left + mu_right * mu_right + c1) * (sigma_left + sigma_right + c2)
    return float(np.mean(numerator / np.maximum(denominator, 1e-9)))


def _edge_delta(left: np.ndarray, right: np.ndarray) -> float:
    left_edges = cv2.Canny(left, 80, 160)
    right_edges = cv2.Canny(right, 80, 160)
    return float(np.mean(cv2.absdiff(left_edges, right_edges)) / 255.0)


def _visual_structure_score(path: str) -> float:
    gray = _read_gray(path, size=(260, 146))
    if gray is None:
        return 0.0
    edges = cv2.Canny(gray, 80, 160)
    edge_ratio = float(np.mean(edges) / 255.0)
    contrast = float(np.std(gray) / 128.0)
    return max(0.0, min(1.0, 0.65 * edge_ratio + 0.35 * min(1.0, contrast)))


def _tokens(text: str) -> set[str]:
    return {token for token in re.findall(r"[a-z0-9]{3,}", text.lower())}


def token_jaccard(left: str, right: str) -> float:
    a = _tokens(left)
    b = _tokens(right)
    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0
    return len(a & b) / max(1, len(a | b))


def compute_frame_metrics(frames: list[dict[str, Any]]) -> list[dict[str, Any]]:
    metrics: list[dict[str, Any]] = []
    previous_gray: np.ndarray | None = None
    previous_hash = ""
    for index, frame in enumerate(frames):
        gray = _read_gray(frame["path"])
        if gray is None:
            continue
        if previous_gray is None:
            absdiff = 0.0
            ssim_delta = 0.0
            edge = 0.0
            hash_delta = 0.0
        else:
            absdiff = float(np.mean(cv2.absdiff(previous_gray, gray)) / 255.0)
            ssim_delta = max(0.0, min(1.0, 1.0 - _ssim_score(previous_gray, gray)))
            edge = _edge_delta(previous_gray, gray)
            hash_delta = min(1.0, _hash_distance(previous_hash, frame.get("image_hash", "")) / 64.0)
        visual_score = 0.40 * absdiff + 0.35 * ssim_delta + 0.15 * edge + 0.10 * hash_delta
        metrics.append(
            {
                **frame,
                "metric_index": index,
                "absdiff": absdiff,
                "ssim_delta": ssim_delta,
                "edge_delta": edge,
                "hash_delta": hash_delta,
                "visual_score": visual_score,
                "boundary_score": visual_score,
                "confidence_components": {
                    "visual": visual_score,
                    "absdiff": absdiff,
                    "ssim_delta": ssim_delta,
                    "edge_delta": edge,
                    "hash_delta": hash_delta,
                    "text_delta": 0.0,
                    "system_delta": 0.0,
                    "action_score": 0.0,
                },
            }
        )
        previous_gray = gray
        previous_hash = frame.get("image_hash", "")
    return metrics


def adaptive_threshold(metrics: list[dict[str, Any]]) -> dict[str, float]:
    scores = [float(metric.get("boundary_score", 0.0)) for metric in metrics[1:]]
    if not scores:
        return {"median": 0.0, "mad": 0.0, "threshold": 1.0, "percentile": 1.0}
    med = median(scores)
    deviations = [abs(score - med) for score in scores]
    mad = median(deviations) or 1e-6
    percentile = float(np.percentile(scores, 88))
    threshold = max(med + 2.5 * mad, percentile)
    if max(scores) - min(scores) < 0.03:
        threshold = float(np.percentile(scores, 94))
    return {"median": float(med), "mad": float(mad), "threshold": float(threshold), "percentile": percentile}


def find_boundary_candidates(
    metrics: list[dict[str, Any]],
    max_segments: int,
    min_stable_seconds: float = 3.0,
) -> tuple[list[dict[str, Any]], dict[str, float]]:
    threshold_info = adaptive_threshold(metrics)
    threshold = threshold_info["threshold"]
    candidates: list[dict[str, Any]] = []
    last_time = -9999.0
    top_scores = sorted(metrics[1:], key=lambda item: item.get("boundary_score", 0.0), reverse=True)
    top_n = min(max(2, max_segments // 3), max(2, len(top_scores) // 4))
    percentile_floor = max(0.01, threshold_info["percentile"] * 0.75)
    top_keep = {
        id(item)
        for item in top_scores[:top_n]
        if float(item.get("boundary_score", 0.0)) >= percentile_floor
    }
    for metric in metrics[1:]:
        score = float(metric.get("boundary_score", 0.0))
        time_sec = float(metric.get("time_sec", 0.0))
        keep_by_score = score >= threshold or id(metric) in top_keep
        if not keep_by_score:
            continue
        if time_sec - last_time < min_stable_seconds:
            if candidates and score > float(candidates[-1].get("boundary_score", 0.0)):
                candidates[-1] = {**metric, "reason": "hysteresis-replace"}
                last_time = time_sec
            continue
        candidates.append({**metric, "reason": "adaptive-threshold" if score >= threshold else "top-percentile"})
        last_time = time_sec
        if len(candidates) >= max_segments - 1:
            break
    return candidates, threshold_info


def _segment_slice(metrics: list[dict[str, Any]], start: int, end: int) -> list[dict[str, Any]]:
    return metrics[max(0, start) : max(start + 1, end)]


def _best_stable_frame(items: list[dict[str, Any]]) -> dict[str, Any]:
    if not items:
        raise ValueError("empty segment")
    return min(items, key=lambda item: (float(item.get("visual_score", 0.0)), -float(item.get("diff_score", 0.0))))


def _state_signature(segment: dict[str, Any]) -> str:
    tokens = sorted(list(_tokens(segment.get("ocr_text", ""))))[:10]
    image_hash = segment.get("image_hash", "")[:8]
    system = segment.get("system", "Other")
    return f"{system}:{image_hash}:{' '.join(tokens)}"


def _assign_screen_states(segments: list[dict[str, Any]]) -> list[dict[str, Any]]:
    states: list[dict[str, Any]] = []
    out = []
    for segment in segments:
        state_id = None
        for state in states:
            same_system = state["system"] == segment.get("system")
            hash_close = _hash_distance(state["image_hash"], segment.get("image_hash", "")) <= 8
            text_close = _similarity(state.get("ocr_text", ""), segment.get("ocr_text", "")) > 0.72
            no_text = not state.get("ocr_text", "").strip() and not segment.get("ocr_text", "").strip()
            if no_text and same_system and segment.get("system") == "Other" and float(segment.get("boundary_score", 0.0)) > 0.02:
                continue
            if same_system and (hash_close or text_close):
                state_id = state["screen_state_id"]
                break
        if state_id is None:
            state_id = len(states) + 1
            states.append(
                {
                    "screen_state_id": state_id,
                    "system": segment.get("system", "Other"),
                    "image_hash": segment.get("image_hash", ""),
                    "ocr_text": segment.get("ocr_text", ""),
                    "signature": _state_signature(segment),
                }
            )
        out.append({**segment, "screen_state_id": state_id})
    return out


def build_initial_segments(
    metrics: list[dict[str, Any]],
    candidates: list[dict[str, Any]],
    max_segments: int,
) -> list[dict[str, Any]]:
    if not metrics:
        return []
    boundary_indices = sorted({int(candidate["metric_index"]) for candidate in candidates})
    spans: list[tuple[int, int, float]] = []
    previous = 0
    for boundary_index in boundary_indices:
        if boundary_index <= previous:
            continue
        spans.append((previous, boundary_index, float(metrics[boundary_index].get("boundary_score", 0.0))))
        previous = boundary_index
    spans.append((previous, len(metrics), 0.0))

    segments: list[dict[str, Any]] = []
    for start, end, boundary_score in spans[:max_segments]:
        items = _segment_slice(metrics, start, end)
        entry = items[0]
        stable = _best_stable_frame(items)
        before = metrics[start - 1] if start > 0 else entry
        after = metrics[end] if end < len(metrics) else stable
        segments.append(
            {
                "event_id": len(segments) + 1,
                "start_time_sec": float(entry.get("time_sec", 0.0)),
                "end_time_sec": float(items[-1].get("time_sec", entry.get("time_sec", 0.0))),
                "time_sec": float(stable.get("time_sec", entry.get("time_sec", 0.0))),
                "before_frame": before.get("path"),
                "entry_frame": entry.get("path"),
                "stable_frame": stable.get("path"),
                "evidence_frame": stable.get("path"),
                "after_frame": after.get("path"),
                "path": stable.get("path"),
                "boundary_score": boundary_score,
                "visual_score": float(stable.get("visual_score", 0.0)),
                "diff_score": float(stable.get("diff_score", 0.0)),
                "image_hash": stable.get("image_hash", ""),
                "segment_frame_count": len(items),
                "confidence_components": stable.get("confidence_components", {}),
            }
        )
    return segments


def select_segment_evidence(segments: list[dict[str, Any]], max_frames: int) -> list[dict[str, Any]]:
    evidence = []
    seen_paths = set()
    roles_by_pass = (("stable_frame",), ("entry_frame", "after_frame"))
    for roles in roles_by_pass:
        for segment in segments:
            for key in roles:
                path = segment.get(key)
                if path and path not in seen_paths and Path(path).exists():
                    seen_paths.add(path)
                    evidence.append(
                        {
                            "event_id": len(evidence) + 1,
                            "segment_id": segment["event_id"],
                            "evidence_role": key,
                            "path": path,
                            "time_sec": segment.get("time_sec", 0),
                            "diff_score": segment.get("diff_score", 0),
                            "image_hash": segment.get("image_hash", ""),
                        }
                    )
                if len(evidence) >= max_frames:
                    return evidence
    return evidence


def _path_for_role(results: list[dict[str, Any]], role: str) -> str | None:
    for result in results:
        if result.get("evidence_role") == role:
            return result.get("path")
    return None


def _ocr_strength(text: str) -> float:
    tokens = _tokens(text)
    if not tokens:
        return 0.0
    token_score = min(1.0, len(tokens) / 18.0)
    char_score = min(1.0, len(text.strip()) / 180.0)
    return max(0.0, min(1.0, 0.55 * token_score + 0.45 * char_score))


def _dialog_signal(text: str) -> float:
    lowered = text.lower()
    if any(term in lowered for term in ["dialog", "pane", "fields", "values", "rows", "columns", "options", "slicer", "chart"]):
        return 0.12
    return 0.0


def _pick_evidence_role(
    segment: dict[str, Any],
    role_text: dict[str, str],
    results: list[dict[str, Any]],
) -> tuple[str, float, float, str]:
    if not results:
        return "stable_frame", 0.0, 0.0, "default stable frame"

    best_role = "stable_frame"
    best_score = -1.0
    best_ocr = 0.0
    best_visual = 0.0
    best_reason = "default stable frame"
    for result in results:
        role = str(result.get("evidence_role") or "stable_frame")
        path = result.get("path") or segment.get(role)
        text = role_text.get(role, "")
        ocr_strength = _ocr_strength(text)
        visual_structure = _visual_structure_score(path) if path else 0.0
        role_bonus = 0.08 if role in {"entry_frame", "after_frame"} else 0.03
        dialog_bonus = _dialog_signal(text)
        score = 0.6 * ocr_strength + 0.3 * visual_structure + role_bonus + dialog_bonus
        if ocr_strength == 0.0:
            score = 0.7 * visual_structure + role_bonus + dialog_bonus
        if score > best_score:
            best_role = role
            best_score = score
            best_ocr = ocr_strength
            best_visual = visual_structure
            if ocr_strength > 0:
                best_reason = f"{role} had the strongest OCR and structure evidence"
            elif dialog_bonus > 0:
                best_reason = f"{role} best exposed the visible dialog or configuration area"
            else:
                best_reason = f"{role} showed the richest visible screen structure"
    return best_role, round(best_ocr, 3), round(best_visual, 3), best_reason


def enrich_segments_with_ocr(
    segments: list[dict[str, Any]],
    max_ocr_frames: int,
    ocr_dir: str | Path,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    evidence = select_segment_evidence(segments, max_ocr_frames)
    ocr_results = run_ocr(evidence, max_frames=max_ocr_frames, ocr_dir=ocr_dir)
    by_segment: dict[int, list[dict[str, Any]]] = {}
    for result in ocr_results:
        by_segment.setdefault(int(result.get("segment_id", 0)), []).append(result)

    enriched: list[dict[str, Any]] = []
    previous_text = ""
    previous_system = "Other"
    for segment in segments:
        results = by_segment.get(int(segment["event_id"]), [])
        role_text = {result.get("evidence_role"): clean_text(result.get("raw_text", "")) for result in results}
        combined = "\n".join(text for text in role_text.values() if text)
        best_role, ocr_strength, visual_structure, evidence_reason = _pick_evidence_role(segment, role_text, results)
        evidence_frame = _path_for_role(results, best_role) or segment.get("evidence_frame")
        system = classify_system(combined, segment.get("stable_frame", ""))
        text_delta = 1.0 - token_jaccard(previous_text, combined)
        system_delta = 1.0 if previous_system != "Other" and system != previous_system else 0.0
        action_hint = _action_hint(combined)
        action_score = 1.0 if action_hint in {"filter", "export", "data entry", "post/save"} else 0.3
        visual = float(segment.get("boundary_score", 0.0))
        boundary_score = 0.45 * visual + 0.25 * text_delta + 0.15 * system_delta + 0.15 * action_score
        components = {
            **segment.get("confidence_components", {}),
            "visual": visual,
            "text_delta": text_delta,
            "system_delta": system_delta,
            "action_score": action_score,
            "boundary_score": boundary_score,
        }
        enriched.append(
            {
                **segment,
                "event_id": len(enriched) + 1,
                "system": system,
                "clean_text": combined,
                "ocr_text": combined,
                "ocr_delta": text_delta,
                "action_hint": action_hint,
                "evidence_frame": evidence_frame,
                "path": evidence_frame or segment.get("path"),
                "boundary_score": boundary_score,
                "confidence_components": components,
                "ocr_by_role": role_text,
                "evidence_selection_reason": evidence_reason,
                "ocr_strength": ocr_strength,
                "visual_structure_score": visual_structure,
            }
        )
        previous_text = combined
        previous_system = system
    return _assign_screen_states(enriched), ocr_results


def smooth_system_continuity(segments: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if len(segments) < 3:
        return segments
    out = [dict(segment) for segment in segments]
    for index in range(1, len(out) - 1):
        current = out[index]
        if current.get("system") != "Other" or str(current.get("ocr_text", "")).strip():
            continue
        left = out[index - 1].get("system")
        right = out[index + 1].get("system")
        if left and left == right and left != "Other":
            current["system"] = left
            current["rule_system_inherited"] = True
    return out


def reject_scroll_only_segments(segments: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not segments:
        return []
    kept = [segments[0]]
    for segment in segments[1:]:
        previous = kept[-1]
        same_system = segment.get("system") == previous.get("system")
        current_text = segment.get("ocr_text", "")
        previous_text = previous.get("ocr_text", "")
        has_text = bool(current_text.strip()) and bool(previous_text.strip())
        text_close = has_text and token_jaccard(current_text, previous_text) > 0.70
        low_boundary = float(segment.get("boundary_score", 0.0)) < 0.12
        same_state = segment.get("screen_state_id") == previous.get("screen_state_id")
        visual_weak = float((segment.get("confidence_components") or {}).get("visual", 0.0) or 0.0) < 0.01
        if has_text:
            scroll_only = same_system and (text_close or same_state) and (low_boundary or same_state)
        else:
            scroll_only = same_system and same_state and visual_weak
        if scroll_only:
            merged = {
                **previous,
                "end_time_sec": segment.get("end_time_sec", previous.get("end_time_sec")),
                "after_frame": segment.get("after_frame") or previous.get("after_frame"),
                "segment_frame_count": previous.get("segment_frame_count", 0) + segment.get("segment_frame_count", 0),
                "scroll_collapsed": True,
            }
            if len(segment.get("ocr_text", "")) > len(previous.get("ocr_text", "")):
                merged.update(
                    {
                        "stable_frame": segment.get("stable_frame"),
                        "evidence_frame": segment.get("evidence_frame"),
                        "path": segment.get("path"),
                        "clean_text": segment.get("clean_text"),
                        "ocr_text": segment.get("ocr_text"),
                    }
                )
            kept[-1] = merged
            continue
        kept.append(segment)
    return [{**segment, "event_id": index + 1} for index, segment in enumerate(kept)]


def _encode_image(path: str) -> str:
    with open(path, "rb") as handle:
        return base64.b64encode(handle.read()).decode("utf-8")


def review_ambiguous_boundaries(
    segments: list[dict[str, Any]],
    max_reviews: int,
    model: str,
) -> list[dict[str, Any]]:
    if max_reviews <= 0 or not os.getenv("OPENAI_API_KEY") or len(segments) < 2:
        return segments
    pairs = []
    for index in range(1, len(segments)):
        score = abs(float(segments[index].get("boundary_score", 0.0)) - 0.16)
        pairs.append((score, index))
    pairs = sorted(pairs, key=lambda item: item[0])[:max_reviews]
    if not pairs:
        return segments

    from openai import OpenAI

    payload = [
        {
            "pair_id": pair_id,
            "left_event_id": segments[index - 1]["event_id"],
            "right_event_id": segments[index]["event_id"],
            "left_system": segments[index - 1].get("system"),
            "right_system": segments[index].get("system"),
            "left_ocr": segments[index - 1].get("ocr_text", "")[:700],
            "right_ocr": segments[index].get("ocr_text", "")[:700],
            "boundary_score": segments[index].get("boundary_score", 0.0),
        }
        for pair_id, (_, index) in enumerate(pairs, start=1)
    ]
    content: list[dict[str, Any]] = [
        {
            "type": "input_text",
            "text": (
                "Decide whether each adjacent segment pair is a real new SOP step or should be merged as same-task/scroll/review. "
                "Return only JSON: [{\"pair_id\":1,\"decision\":\"keep|merge\",\"reason\":\"...\"}]."
            ),
        },
        {"type": "input_text", "text": json.dumps(payload, ensure_ascii=False)},
    ]
    for pair_id, (_, index) in enumerate(pairs, start=1):
        for side, segment in (("left", segments[index - 1]), ("right", segments[index])):
            image_path = segment.get("stable_frame") or segment.get("path")
            if image_path and Path(image_path).exists():
                try:
                    content.append({"type": "input_text", "text": f"{side} screenshot for pair_id {pair_id}:"})
                    content.append(
                        {
                            "type": "input_image",
                            "image_url": f"data:image/jpeg;base64,{_encode_image(image_path)}",
                            "detail": "low",
                        }
                    )
                except Exception:
                    pass
    try:
        response = OpenAI().responses.create(
            model=model,
            input=[{"role": "user", "content": content}],
            temperature=0.1,
        )
        text = getattr(response, "output_text", "") or ""
        match = re.search(r"\[[\s\S]*\]", text.strip())
        decisions = json.loads(match.group(0) if match else text)
    except Exception:
        time.sleep(1)
        return segments

    merge_indices = set()
    for decision in decisions if isinstance(decisions, list) else []:
        if decision.get("decision") != "merge":
            continue
        pair_id = int(decision.get("pair_id", 0))
        if 1 <= pair_id <= len(pairs):
            merge_indices.add(pairs[pair_id - 1][1])
    if not merge_indices:
        return segments

    merged: list[dict[str, Any]] = []
    for index, segment in enumerate(segments):
        if index in merge_indices and merged:
            previous = merged[-1]
            merged[-1] = {
                **previous,
                "end_time_sec": segment.get("end_time_sec", previous.get("end_time_sec")),
                "after_frame": segment.get("after_frame") or previous.get("after_frame"),
                "ambiguous_boundary_merged": True,
                "segment_frame_count": previous.get("segment_frame_count", 0) + segment.get("segment_frame_count", 0),
            }
            continue
        merged.append(segment)
    return [{**segment, "event_id": index + 1} for index, segment in enumerate(merged)]


def segment_frames(
    frames: list[dict[str, Any]],
    max_segments: int,
    max_ocr_frames: int,
    ocr_dir: str | Path,
    ambiguous_reviews: int = 0,
    model: str = "gpt-5.5",
) -> dict[str, Any]:
    metrics = compute_frame_metrics(frames)
    duration = float(metrics[-1].get("time_sec", 0.0)) - float(metrics[0].get("time_sec", 0.0)) if len(metrics) > 1 else 0.0
    min_stable_seconds = 1.0 if duration < 20 else 3.0
    candidates, threshold_info = find_boundary_candidates(
        metrics,
        max_segments=max_segments,
        min_stable_seconds=min_stable_seconds,
    )
    initial = build_initial_segments(metrics, candidates, max_segments=max_segments)
    enriched, ocr_results = enrich_segments_with_ocr(initial, max_ocr_frames=max_ocr_frames, ocr_dir=ocr_dir)
    smoothed = smooth_system_continuity(enriched)
    collapsed = reject_scroll_only_segments(smoothed)
    reviewed = review_ambiguous_boundaries(collapsed, max_reviews=ambiguous_reviews, model=model)
    final_segments = reviewed[:max_segments]
    for index, segment in enumerate(final_segments):
        previous_state = final_segments[index - 1].get("screen_state_id") if index > 0 else None
        next_state = final_segments[index + 1].get("screen_state_id") if index + 1 < len(final_segments) else None
        segment["dense_repeated_run"] = bool(
            segment.get("screen_state_id")
            and (segment.get("screen_state_id") == previous_state or segment.get("screen_state_id") == next_state)
        )
    states = []
    seen_states = set()
    for segment in final_segments:
        state_id = segment.get("screen_state_id")
        if state_id in seen_states:
            continue
        seen_states.add(state_id)
        states.append(
            {
                "screen_state_id": state_id,
                "system": segment.get("system", "Other"),
                "signature": _state_signature(segment),
                "first_event_id": segment.get("event_id"),
            }
        )
    return {
        "frame_metrics": metrics,
        "threshold_info": threshold_info,
        "boundary_candidates": candidates,
        "initial_segments": initial,
        "ocr_results": ocr_results,
        "screen_states": states,
        "event_segments": final_segments,
    }


def segmentation_report(segmentation: dict[str, Any]) -> str:
    threshold = segmentation.get("threshold_info", {})
    segments = segmentation.get("event_segments", [])
    states = segmentation.get("screen_states", [])
    candidates = segmentation.get("boundary_candidates", [])
    lines = [
        "# Segmentation Report",
        "",
        f"- Frame metrics: {len(segmentation.get('frame_metrics', []))}",
        f"- Boundary candidates: {len(candidates)}",
        f"- Screen states: {len(states)}",
        f"- Final event segments: {len(segments)}",
        f"- Threshold: {threshold.get('threshold', 0):.4f}",
        f"- Median/MAD: {threshold.get('median', 0):.4f} / {threshold.get('mad', 0):.4f}",
        "",
        "## Event Segments",
    ]
    for segment in segments:
        lines.append(
            "- "
            f"#{segment.get('event_id')} "
            f"{segment.get('start_time_sec', 0):.1f}s-{segment.get('end_time_sec', 0):.1f}s "
            f"system={segment.get('system')} "
            f"state={segment.get('screen_state_id')} "
            f"score={segment.get('boundary_score', 0):.4f} "
            f"hint={segment.get('action_hint')}"
        )
    return "\n".join(lines) + "\n"
