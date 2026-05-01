from __future__ import annotations

import sys
import tempfile
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pipeline.capabilities import capability_status
from pipeline.ocr import ocr_status, run_ocr
from pipeline.runtime_config import runtime_config_status


def build_ocr_image(path: Path) -> None:
    image = np.full((180, 560, 3), 255, dtype=np.uint8)
    cv2.putText(image, "Invoice Status Posted", (25, 95), cv2.FONT_HERSHEY_SIMPLEX, 1.1, (0, 0, 0), 2)
    cv2.imwrite(str(path), image)


def main() -> int:
    config = runtime_config_status()
    status = capability_status()
    ocr = ocr_status()
    print(f".env found: {config['dotenv_found']} ({config['dotenv_path']})")
    print(f"Streamlit secrets found: {config['streamlit_secrets_found']} ({config['streamlit_secrets_path']})")
    print(f"OpenAI configured: {status['openai_configured']}")
    print(f"OpenAI key source: {config['openai_key_source']}")
    print(f"OpenAI model: {config['openai_model']} ({config['openai_model_source']})")
    print(f"Generation mode: {status['generation_mode']}")
    print(f"Tesseract available: {ocr.get('available')}")
    print(f"Tesseract command: {ocr.get('cmd')}")
    print(f"Tesseract version: {ocr.get('version')}")
    if ocr.get("error"):
        print(f"Tesseract error: {ocr['error']}")

    with tempfile.TemporaryDirectory() as tmp:
        image_path = Path(tmp) / "ocr_smoke.png"
        build_ocr_image(image_path)
        result = run_ocr([{"event_id": 1, "path": str(image_path)}], max_frames=1, ocr_dir=Path(tmp) / "ocr")
        text = (result[0].get("raw_text") or "").strip() if result else ""
        print(f"OCR smoke text: {text!r}")
        if ocr.get("available") and not text:
            print("OCR smoke check failed.")
            return 1

    if not status["openai_configured"] and not ocr.get("available"):
        print("No production evidence source is available.")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
