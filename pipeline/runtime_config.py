from __future__ import annotations

import os
import tomllib
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DOTENV_PATH = REPO_ROOT / ".env"
DEFAULT_STREAMLIT_SECRETS_PATH = REPO_ROOT / ".streamlit" / "secrets.toml"

_env_before_dotenv: dict[str, str] = {}
_dotenv_path = DEFAULT_DOTENV_PATH
_dotenv_values: dict[str, str] = {}
_streamlit_secrets_path = DEFAULT_STREAMLIT_SECRETS_PATH
_streamlit_secret_values: dict[str, Any] = {}


def _truthy(value: str | None) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def _parse_dotenv(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    try:
        from dotenv import dotenv_values

        return {key: str(value) for key, value in dotenv_values(path).items() if key and value not in (None, "")}
    except Exception:
        values: dict[str, str] = {}
        for raw_line in path.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip().strip("'\"")
            if key and value:
                values[key] = value
        return values


def _read_streamlit_secrets(path: Path) -> dict[str, Any]:
    values: dict[str, Any] = {}
    if path.exists():
        try:
            values.update(tomllib.loads(path.read_text(encoding="utf-8")))
        except Exception:
            pass
    try:
        import streamlit as st

        secrets = getattr(st, "secrets", {})
        for key in ("OPENAI_API_KEY", "OPENAI_MODEL", "TESSERACT_CMD"):
            try:
                if key in secrets and secrets[key]:
                    values[key] = secrets[key]
            except Exception:
                continue
    except Exception:
        pass
    return values


def load_runtime_config(
    dotenv_path: str | Path | None = None,
    streamlit_secrets_path: str | Path | None = None,
) -> None:
    global _env_before_dotenv, _dotenv_path, _dotenv_values
    global _streamlit_secrets_path, _streamlit_secret_values

    _env_before_dotenv = dict(os.environ)
    _dotenv_path = Path(dotenv_path or os.getenv("VIDEO2SOP_DOTENV_PATH") or DEFAULT_DOTENV_PATH)
    _streamlit_secrets_path = Path(
        streamlit_secrets_path
        or os.getenv("VIDEO2SOP_STREAMLIT_SECRETS_PATH")
        or DEFAULT_STREAMLIT_SECRETS_PATH
    )
    _dotenv_values = _parse_dotenv(_dotenv_path)
    for key, value in _dotenv_values.items():
        os.environ.setdefault(key, value)
    _streamlit_secret_values = _read_streamlit_secrets(_streamlit_secrets_path)


def get_config_with_source(key: str, default: str | None = None) -> tuple[str | None, str]:
    env_value = os.environ.get(key)
    dotenv_value = _dotenv_values.get(key)
    if env_value:
        if key in _env_before_dotenv or key not in _dotenv_values or env_value != dotenv_value:
            return env_value, "environment"
    if dotenv_value:
        return dotenv_value, ".env"
    secret_value = _streamlit_secret_values.get(key)
    if secret_value not in (None, ""):
        return str(secret_value), "streamlit secrets"
    if env_value:
        return env_value, "environment"
    return default, "default"


def get_config(key: str, default: str | None = None) -> str | None:
    return get_config_with_source(key, default=default)[0]


def config_source(key: str) -> str:
    return get_config_with_source(key)[1]


def has_openai_key() -> bool:
    if _truthy(os.getenv("VIDEO2SOP_DISABLE_OPENAI")):
        return False
    value = get_config("OPENAI_API_KEY")
    return bool(value and value.strip() and value.strip() != "replace_me")


def runtime_config_status() -> dict[str, Any]:
    openai_value, openai_source = get_config_with_source("OPENAI_API_KEY")
    model_value, model_source = get_config_with_source("OPENAI_MODEL", "gpt-5.5")
    return {
        "repo_root": str(REPO_ROOT),
        "dotenv_path": str(_dotenv_path),
        "dotenv_found": _dotenv_path.exists(),
        "streamlit_secrets_path": str(_streamlit_secrets_path),
        "streamlit_secrets_found": _streamlit_secrets_path.exists(),
        "openai_configured": has_openai_key(),
        "openai_key_source": "disabled" if _truthy(os.getenv("VIDEO2SOP_DISABLE_OPENAI")) else openai_source,
        "openai_key_present": bool(openai_value and str(openai_value).strip() and openai_value != "replace_me"),
        "openai_model": model_value,
        "openai_model_source": model_source,
    }


load_runtime_config()
