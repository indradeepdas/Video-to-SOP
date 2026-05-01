from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import os
from pathlib import Path
import shutil
import subprocess
from typing import Any

import cv2

from pipeline.runtime_config import get_config


COMMON_TESSERACT_PATHS = [
    r"C:\Program Files\Tesseract-OCR\tesseract.exe",
    r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
]


def resolve_tesseract_cmd() -> str | None:
    candidates = []
    env_cmd = get_config("TESSERACT_CMD")
    if env_cmd:
        candidates.append(env_cmd)
    path_cmd = shutil.which("tesseract")
    if path_cmd:
        candidates.append(path_cmd)
    candidates.extend(COMMON_TESSERACT_PATHS)

    for candidate in candidates:
        if not candidate:
            continue
        path = Path(candidate)
        if path.exists():
            return str(path)
        if shutil.which(candidate):
            return str(candidate)
    return None


def configure_tesseract() -> str | None:
    cmd = resolve_tesseract_cmd()
    if not cmd:
        return None
    try:
        import pytesseract

        pytesseract.pytesseract.tesseract_cmd = cmd
    except Exception:
        pass
    return cmd


def tesseract_available() -> bool:
    return configure_tesseract() is not None


def ocr_status() -> dict[str, Any]:
    cmd = configure_tesseract()
    if not cmd:
        return {
            "available": False,
            "cmd": None,
            "version": None,
            "error": "Tesseract executable was not found via TESSERACT_CMD, PATH, or common Windows install paths.",
        }
    try:
        completed = subprocess.run(
            [cmd, "--version"],
            capture_output=True,
            text=True,
            timeout=8,
            check=False,
        )
        version = (completed.stdout or completed.stderr or "").splitlines()[0].strip()
        if completed.returncode != 0:
            return {"available": False, "cmd": cmd, "version": version or None, "error": completed.stderr.strip()}
        return {"available": True, "cmd": cmd, "version": version, "error": None}
    except Exception as exc:
        return {"available": False, "cmd": cmd, "version": None, "error": str(exc)}


def _preprocess_for_ocr(image_path: str, output_path: str) -> str:
    image = cv2.imread(image_path)
    if image is None:
        return image_path
    height, width = image.shape[:2]
    if width > 1100:
        scale = 1100 / float(width)
        image = cv2.resize(image, (1100, max(1, int(height * scale))), interpolation=cv2.INTER_AREA)
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    gray = cv2.resize(gray, None, fx=1.2, fy=1.2, interpolation=cv2.INTER_CUBIC)
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
        configure_tesseract()
        import pytesseract
        from PIL import Image
    except Exception:
        return ""

    try:
        image = Image.open(image_path)
        primary = pytesseract.image_to_string(image, config="--oem 3 --psm 6") or ""
        if len(primary.strip()) >= 24:
            return primary
        secondary = pytesseract.image_to_string(image, config="--oem 3 --psm 11") or ""
        return max([primary, secondary], key=len, default="")
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

    def process_frame(item: tuple[int, dict[str, Any]]) -> dict[str, Any]:
        event_index, frame = item
        path = str(Path(frame["path"]))
        ocr_image_path = path
        if ocr_dir and available:
            ocr_image_path = _preprocess_for_ocr(path, str(Path(ocr_dir) / f"ocr_{event_index:04d}.png"))
        raw_text = _ocr_with_tesseract(ocr_image_path) if available else ""
        return {
            **frame,
            "event_id": event_index,
            "raw_text": raw_text,
            "ocr_available": available,
            "ocr_image_path": ocr_image_path,
        }

    items = list(enumerate(ocr_frames, start=1))
    if available and len(items) > 1:
        workers = min(4, len(items), max(1, os.cpu_count() or 1))
        with ThreadPoolExecutor(max_workers=workers) as executor:
            return list(executor.map(process_frame, items))

    results = []
    for item in items:
        results.append(process_frame(item))
    return results
