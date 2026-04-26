from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from pipeline.capabilities import DIAGNOSTIC_ONLY, LOCAL_OCR_DRAFT, PRODUCTION_VISION, generation_mode_after_ocr
from pipeline.ocr import COMMON_TESSERACT_PATHS, resolve_tesseract_cmd


class CapabilityTests(unittest.TestCase):
    def test_tesseract_cmd_env_override_is_resolved(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            fake = Path(tmp) / "tesseract.exe"
            fake.write_text("", encoding="utf-8")
            with mock.patch.dict(os.environ, {"TESSERACT_CMD": str(fake)}, clear=False):
                self.assertEqual(resolve_tesseract_cmd(), str(fake))

    def test_common_windows_tesseract_path_is_resolved_when_present(self) -> None:
        installed = [path for path in COMMON_TESSERACT_PATHS if Path(path).exists()]
        if not installed:
            self.skipTest("Native Tesseract is not installed at a common Windows path.")
        with mock.patch.dict(os.environ, {"TESSERACT_CMD": ""}, clear=False), mock.patch("shutil.which", return_value=None):
            self.assertEqual(resolve_tesseract_cmd(), installed[0])

    def test_generation_mode_after_ocr(self) -> None:
        self.assertEqual(generation_mode_after_ocr(True, 0), PRODUCTION_VISION)
        self.assertEqual(generation_mode_after_ocr(False, 3), LOCAL_OCR_DRAFT)
        self.assertEqual(generation_mode_after_ocr(False, 0), DIAGNOSTIC_ONLY)


if __name__ == "__main__":
    unittest.main()
