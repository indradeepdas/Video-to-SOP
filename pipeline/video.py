from __future__ import annotations

import math
from pathlib import Path
from typing import Any

import cv2
import numpy as np


def _resize_for_width(frame: np.ndarray, max_width: int) -> np.ndarray:
    height, width = frame.shape[:2]
    if width <= max_width:
        return frame
    scale = max_width / float(width)
    return cv2.resize(frame, (max_width, int(height * scale)), interpolation=cv2.INTER_AREA)


def _gray_thumb(frame: np.ndarray) -> np.ndarray:
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    return cv2.resize(gray, (160, 90), interpolation=cv2.INTER_AREA)


def _diff_score(previous: np.ndarray | None, current: np.ndarray) -> float:
    if previous is None:
        return 0.0
    diff = cv2.absdiff(previous, current)
    return float(np.mean(diff) / 255.0)


def _average_hash(frame: np.ndarray, size: int = 8) -> str:
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    small = cv2.resize(gray, (size, size), interpolation=cv2.INTER_AREA)
    mean = float(np.mean(small))
    bits = ["1" if value > mean else "0" for value in small.flatten()]
    return f"{int(''.join(bits), 2):016x}"


def _hash_distance(left: str, right: str) -> int:
    try:
        return (int(left, 16) ^ int(right, 16)).bit_count()
    except Exception:
        return 64


def extract_frames(
    video_path: str | Path,
    output_dir: str | Path,
    interval_seconds: float = 4.5,
    max_width: int = 1280,
    max_frames: int = 850,
) -> list[dict[str, Any]]:
    video_path = Path(video_path)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    capture = cv2.VideoCapture(str(video_path))
    if not capture.isOpened():
        raise RuntimeError(f"Could not open video: {video_path}")

    fps = capture.get(cv2.CAP_PROP_FPS) or 30.0
    total_frames = int(capture.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    duration = total_frames / fps if total_frames > 0 and fps > 0 else 0
    if duration <= 0:
        duration = max(1.0, max_frames * interval_seconds)

    count = min(max_frames, max(1, int(math.ceil(duration / interval_seconds))))
    times = [min(duration, i * interval_seconds) for i in range(count)]
    if times[-1] < duration - 1:
        times.append(duration)

    frames: list[dict[str, Any]] = []
    previous_thumb: np.ndarray | None = None

    for index, time_sec in enumerate(times):
        capture.set(cv2.CAP_PROP_POS_MSEC, max(0, time_sec * 1000))
        ok, frame = capture.read()
        if not ok or frame is None:
            continue
        frame = _resize_for_width(frame, max_width)
        thumb = _gray_thumb(frame)
        score = _diff_score(previous_thumb, thumb)
        previous_thumb = thumb

        out_path = output_dir / f"frame_{index:04d}_{int(time_sec):05d}s.jpg"
        cv2.imwrite(str(out_path), frame, [int(cv2.IMWRITE_JPEG_QUALITY), 82])
        height, width = frame.shape[:2]
        frames.append(
            {
                "frame_id": index,
                "time_sec": float(time_sec),
                "path": str(out_path),
                "width": int(width),
                "height": int(height),
                "diff_score": score,
                "image_hash": _average_hash(frame),
            }
        )

    capture.release()
    return frames


def select_representative_frames(
    frames: list[dict[str, Any]],
    max_selected: int = 80,
    even_ratio: float = 0.4,
    min_gap_seconds: float = 8.0,
) -> list[dict[str, Any]]:
    if len(frames) <= max_selected:
        return [dict(frame, selected_reason="all") for frame in frames]

    selected: dict[int, dict[str, Any]] = {}

    def can_add(frame: dict[str, Any], gap: float) -> bool:
        for existing in selected.values():
            too_close = abs(frame["time_sec"] - existing["time_sec"]) < gap
            duplicate_image = _hash_distance(frame.get("image_hash", ""), existing.get("image_hash", "")) <= 4
            if too_close or duplicate_image:
                return False
        return True

    def add(frame: dict[str, Any], reason: str, gap: float = min_gap_seconds, force: bool = False) -> None:
        if len(selected) >= max_selected:
            return
        frame_id = int(frame["frame_id"])
        if frame_id in selected:
            return
        if force or not selected or can_add(frame, gap):
            selected[frame_id] = dict(frame, selected_reason=reason)

    add(frames[0], "first", gap=0, force=True)
    add(frames[-1], "last", gap=0, force=True)

    even_target = max(1, int(max_selected * even_ratio))
    stride = max(1, len(frames) // even_target)
    for i in range(0, len(frames), stride):
        add(frames[i], "even")

    for frame in sorted(frames, key=lambda item: item.get("diff_score", 0), reverse=True):
        if float(frame.get("diff_score", 0)) < 0.01:
            continue
        add(frame, "change")
        if len(selected) >= max_selected:
            break

    if len(selected) < max_selected:
        for frame in frames:
            add(frame, "fill", gap=max(2.0, min_gap_seconds / 2))
            if len(selected) >= max_selected:
                break

    return sorted(selected.values(), key=lambda item: item["time_sec"])
