"""Configuration loaded afresh for every screenshot request."""

from __future__ import annotations

import os
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path
from typing import Any

import yaml
from platformdirs import user_cache_dir, user_config_dir

ENV_PREFIX = "SCREENSHOT_TOOL"
CONFIG_DIR = Path(user_config_dir("screenshot-tool"))
DEFAULT_CONFIG_PATH = CONFIG_DIR / "config.yaml"
DEFAULT_FORMATS = {"png", "jpg", "jpeg", "webp"}


def runtime_dir() -> Path:
    root = Path(os.environ.get("XDG_RUNTIME_DIR", f"/run/user/{os.getuid()}"))
    if not root.is_dir():
        root = Path(user_cache_dir("screenshot-tool")) / "runtime"
    return root / "screenshot-tool"


@dataclass
class Config:
    wayland_capture: str = "wayland-capture"
    output_dir: Path = field(
        default_factory=lambda: Path.home() / "Pictures" / "screenshots"
    )
    silent_output_dir: Path = field(default_factory=lambda: runtime_dir() / "captures")
    hooks_dir: Path | None = field(default_factory=lambda: CONFIG_DIR / "hooks")
    default_format: str = "png"
    default_quality: int = 90
    enable_sound: bool = True
    enable_notification: bool = True
    enable_clipboard: bool = True
    include_window_title: bool = False

    def __post_init__(self) -> None:
        for key in ("output_dir", "silent_output_dir", "hooks_dir"):
            value = getattr(self, key)
            if value is not None and not isinstance(value, Path):
                setattr(self, key, Path(value).expanduser())


def config_defaults() -> dict[str, Any]:
    return _serialize(Config())


def _serialize(config: Config) -> dict[str, Any]:
    return {
        key: str(value) if isinstance(value, Path) else value
        for key, value in asdict(config).items()
    }


def config_to_dict(config: Config) -> dict[str, Any]:
    return _serialize(config)


def resolve_config_path(config_path: Path | None = None) -> Path:
    configured = os.environ.get(f"{ENV_PREFIX}_CONFIG") or os.environ.get(
        f"{ENV_PREFIX}_CONFIG_PATH"
    )
    return config_path or (
        Path(configured).expanduser() if configured else DEFAULT_CONFIG_PATH
    )


def _file_values(path: Path, strict: bool) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        values = yaml.safe_load(path.read_text()) or {}
    except Exception as exc:
        if strict:
            raise ValueError(f"Failed to parse config file {path}: {exc}") from exc
        return {}
    if not isinstance(values, dict):
        if strict:
            raise ValueError(f"Config file {path} must be a mapping")
        return {}
    # Old runtime/native-helper keys are intentionally ignored during migration.
    return values


def _environment_values() -> dict[str, Any]:
    values: dict[str, Any] = {}
    valid = {item.name for item in fields(Config)}
    for key in valid:
        raw = os.environ.get(f"{ENV_PREFIX}_{key.upper()}")
        if raw is None:
            continue
        if key.startswith("enable_") or key == "include_window_title":
            values[key] = raw.lower() in {"1", "true", "yes", "on"}
        elif key == "default_quality":
            try:
                values[key] = int(raw)
            except ValueError:
                continue
        else:
            values[key] = raw
    return values


def load_config(
    config_path: Path | None = None,
    overrides: dict[str, Any] | None = None,
    strict: bool = False,
) -> Config:
    values = config_defaults()
    values.update(_file_values(resolve_config_path(config_path), strict))
    values.update(_environment_values())
    values.update(
        {key: value for key, value in (overrides or {}).items() if value is not None}
    )
    valid = {item.name for item in fields(Config)}
    return Config(**{key: value for key, value in values.items() if key in valid})


def config_schema() -> dict[str, Any]:
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "type": "object",
        "properties": {
            "wayland_capture": {"type": "string"},
            "output_dir": {"type": "string"},
            "silent_output_dir": {"type": "string"},
            "hooks_dir": {"type": ["string", "null"]},
            "default_format": {"type": "string", "enum": sorted(DEFAULT_FORMATS)},
            "default_quality": {"type": "integer", "minimum": 1, "maximum": 100},
            "enable_sound": {"type": "boolean"},
            "enable_notification": {"type": "boolean"},
            "enable_clipboard": {"type": "boolean"},
            "include_window_title": {"type": "boolean"},
        },
        "additionalProperties": False,
    }


def validate_config_file(config_path: Path | None = None) -> list[str]:
    path = resolve_config_path(config_path)
    try:
        values = _file_values(path, True)
    except ValueError as exc:
        return [str(exc)]
    properties = config_schema()["properties"]
    errors = [
        f"Unknown configuration key: {key}" for key in values if key not in properties
    ]
    fmt = values.get("default_format")
    if fmt is not None and fmt not in DEFAULT_FORMATS:
        errors.append(
            f"default_format must be one of: {', '.join(sorted(DEFAULT_FORMATS))}"
        )
    quality = values.get("default_quality")
    if quality is not None and (
        isinstance(quality, bool)
        or not isinstance(quality, int)
        or not 1 <= quality <= 100
    ):
        errors.append("default_quality must be an integer from 1 to 100")
    return errors
