from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

BASE_DIR = Path(__file__).resolve().parent
DEFAULT_CONFIG_PATH = BASE_DIR / "config.yaml"

def _as_mapping(value: Any, name: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"Invalid config format: '{name}' must be a mapping")
    return value


def load_shared_config() -> tuple[dict[str, dict[str, Any]], Path]:
    resolved_path = DEFAULT_CONFIG_PATH.resolve()
    if not resolved_path.exists():
        raise FileNotFoundError(f"Config file not found: {resolved_path}")

    raw = yaml.safe_load(resolved_path.read_text(encoding="utf-8"))
    root = _as_mapping(raw, "root")
    required_sections = ("common", "lightgbm-train", "lightgbm-evaluate")
    for section in required_sections:
        if section not in root:
            raise ValueError(f"Missing required config section: '{section}'")

    config = {section: _as_mapping(root[section], section) for section in required_sections}
    return config, resolved_path
