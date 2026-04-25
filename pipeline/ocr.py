from __future__ import annotations

from pathlib import Path
import shutil
from typing import Any

import cv2


def tesseract_available() -> bool:
    return shutil.which("tesseract") is not None


def _preprocess_for_ocr(image_path: str, output_path: str) -> str:
    image = cv2.imread(image_path)
    if image is None:
        return image_path
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    gray = cv2.resize(gray, None, fx=1.35, fy=1.35, interpolation=cv2.INTER_CUBIC)
    gray = cv2.bilateralFilter(gray, 5, 35, 35)
    threshold = cv2.adaptiveThreshold(
        gray,
        255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY,
        31,
        7,
    )
    cv2.imwrite(output_path, threshold)
    return output_path


def _ocr_with_tesseract(image_path: str) -> str:
    try:
        import pytesseract
        from PIL import Image
    except Exception:
        return ""

    try:
        image = Image.open(image_path)
        configs = ["--oem 3 --psm 6", "--oem 3 --psm 11"]
        results = [pytesseract.image_to_string(image, config=config) or "" for config in configs]
        return max(results, key=len, default="")
    except Exception:
        return ""


def run_ocr(frames: list[dict[str, Any]], max_frames: int = 60, ocr_dir: str | Path | None = None) -> list[dict[str, Any]]:
    if not frames:
        return []
    available = tesseract_available()
    if ocr_dir:
        Path(ocr_dir).mkdir(parents=True, exist_ok=True)

    if len(frames) <= max_frames:
        ocr_frames = frames
    else:
        stride = max(1, len(frames) // max_frames)
        ocr_frames = frames[::stride][:max_frames]
        if frames[-1] not in ocr_frames:
            ocr_frames[-1] = frames[-1]

    results = []
    for event_index, frame in enumerate(ocr_frames, start=1):
        path = str(Path(frame["path"]))
        ocr_image_path = path
        if ocr_dir and available:
            ocr_image_path = _preprocess_for_ocr(path, str(Path(ocr_dir) / f"ocr_{event_index:04d}.png"))
        raw_text = _ocr_with_tesseract(ocr_image_path) if available else ""
        results.append(
            {
                **frame,
                "event_id": event_index,
                "raw_text": raw_text,
                "ocr_available": available,
                "ocr_image_path": ocr_image_path,
            }
        )
    return results
