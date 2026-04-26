from __future__ import annotations

import os
from typing import Any

from pipeline.ocr import ocr_status


PRODUCTION_VISION = "production_vision"
LOCAL_OCR_DRAFT = "local_ocr_draft"
DIAGNOSTIC_ONLY = "diagnostic_only"


def openai_configured() -> bool:
    return bool(os.getenv("OPENAI_API_KEY"))


def capability_status() -> dict[str, Any]:
    openai_ready = openai_configured()
    ocr = ocr_status()
    if openai_ready:
        mode = PRODUCTION_VISION
    elif ocr.get("available"):
        mode = LOCAL_OCR_DRAFT
    else:
        mode = DIAGNOSTIC_ONLY
    return {
        "generation_mode": mode,
        "openai_configured": openai_ready,
        "ocr_available": bool(ocr.get("available")),
        "ocr_status": ocr,
    }


def generation_mode_after_ocr(openai_ready: bool, ocr_non_empty_count: int) -> str:
    if openai_ready:
        return PRODUCTION_VISION
    if ocr_non_empty_count > 0:
        return LOCAL_OCR_DRAFT
    return DIAGNOSTIC_ONLY
