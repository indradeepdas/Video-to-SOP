from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from pipeline.capabilities import DIAGNOSTIC_ONLY, LOCAL_OCR_DRAFT, PRODUCTION_VISION, generation_mode_after_ocr, openai_configured
from pipeline.ocr import COMMON_TESSERACT_PATHS, resolve_tesseract_cmd
from pipeline.runtime_config import get_config, get_config_with_source, load_runtime_config


class CapabilityTests(unittest.TestCase):
    def tearDown(self) -> None:
        load_runtime_config()

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

    def test_dotenv_values_are_loaded_automatically(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            env_file = Path(tmp) / ".env"
            env_file.write_text("OPENAI_API_KEY=from_dotenv\nOPENAI_MODEL=test-model\n", encoding="utf-8")
            with mock.patch.dict(os.environ, {"OPENAI_API_KEY": "", "OPENAI_MODEL": ""}, clear=False):
                os.environ.pop("OPENAI_API_KEY", None)
                os.environ.pop("OPENAI_MODEL", None)
                load_runtime_config(dotenv_path=env_file, streamlit_secrets_path=Path(tmp) / "missing.toml")
                self.assertEqual(get_config("OPENAI_API_KEY"), "from_dotenv")
                self.assertEqual(get_config_with_source("OPENAI_API_KEY")[1], ".env")
                self.assertEqual(get_config("OPENAI_MODEL"), "test-model")

    def test_environment_overrides_dotenv(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            env_file = Path(tmp) / ".env"
            env_file.write_text("OPENAI_API_KEY=from_dotenv\n", encoding="utf-8")
            with mock.patch.dict(os.environ, {"OPENAI_API_KEY": "from_environment"}, clear=False):
                load_runtime_config(dotenv_path=env_file, streamlit_secrets_path=Path(tmp) / "missing.toml")
                value, source = get_config_with_source("OPENAI_API_KEY")
                self.assertEqual(value, "from_environment")
                self.assertEqual(source, "environment")

    def test_streamlit_secret_file_is_used_when_env_and_dotenv_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            secrets_file = Path(tmp) / "secrets.toml"
            secrets_file.write_text('OPENAI_API_KEY = "from_secrets"\n', encoding="utf-8")
            with mock.patch.dict(os.environ, {"OPENAI_API_KEY": ""}, clear=False):
                os.environ.pop("OPENAI_API_KEY", None)
                load_runtime_config(dotenv_path=Path(tmp) / "missing.env", streamlit_secrets_path=secrets_file)
                value, source = get_config_with_source("OPENAI_API_KEY")
                self.assertEqual(value, "from_secrets")
                self.assertEqual(source, "streamlit secrets")

    def test_disable_openai_blocks_configured_key(self) -> None:
        with mock.patch.dict(os.environ, {"OPENAI_API_KEY": "test", "VIDEO2SOP_DISABLE_OPENAI": "1"}, clear=False):
            load_runtime_config(dotenv_path=Path("missing.env"), streamlit_secrets_path=Path("missing.toml"))
            self.assertFalse(openai_configured())


if __name__ == "__main__":
    unittest.main()
