"""Configuration loader for MyVote-D.

Loads ``myvote/config.yaml`` once and exposes a cached singleton. Supports
dotted-path access, e.g. ``cfg("detection.psd.duplicate_threshold")``.

Unlike upstream (pydantic-settings + .env), MyVote-D keeps its YAML config
**isolated** inside the package. Paths are anchored to the ``myvote`` package
directory so the subsystem works regardless of the current working directory.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

# The ``myvote`` package directory (this file lives at myvote/config.py).
PACKAGE_DIR = Path(__file__).resolve().parent
# Kept as an alias for backward compatibility; anchored to the package so the
# SQLite DB lands in ``myvote/data/`` (never the repo root, never upstream's DB).
PROJECT_ROOT = PACKAGE_DIR
DEFAULT_CONFIG_PATH = PACKAGE_DIR / "config.yaml"


class Config:
    """Thin wrapper around the parsed YAML document."""

    def __init__(self, data: dict[str, Any], path: Path | None = None):
        self._data = data
        self.path = path

    def get(self, dotted_key: str, default: Any = None) -> Any:
        """Return a nested value by dotted path, or ``default`` if missing."""
        node: Any = self._data
        for part in dotted_key.split("."):
            if isinstance(node, dict) and part in node:
                node = node[part]
            else:
                return default
        return node

    def require(self, dotted_key: str) -> Any:
        """Return a nested value or raise ``KeyError`` if missing."""
        sentinel = object()
        value = self.get(dotted_key, sentinel)
        if value is sentinel:
            raise KeyError(f"Missing required config key: {dotted_key}")
        return value

    def as_dict(self) -> dict[str, Any]:
        return dict(self._data)


def load_config(path: str | Path | None = None) -> Config:
    cfg_path = Path(path) if path is not None else DEFAULT_CONFIG_PATH
    with open(cfg_path, "r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh)
    if not isinstance(data, dict):
        raise ValueError(f"Config at {cfg_path} did not parse to a mapping")
    return Config(data, cfg_path)


@lru_cache(maxsize=1)
def get_config() -> Config:
    """Cached accessor used across the app. Call ``get_config.cache_clear()``
    in tests that reload config."""
    return load_config()
