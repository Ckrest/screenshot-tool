"""Configuration management for Screenshot Tool.

Configuration priority (highest to lowest):
1. CLI overrides (passed to load_config)
2. Environment variables (SCREENSHOT_TOOL_*)
3. Config file (~/.config/screenshot-tool/config.yaml)
4. Built-in defaults
"""

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, Any

import yaml
from platformdirs import user_config_dir, user_data_dir, user_cache_dir

ENV_PREFIX = "SCREENSHOT_TOOL"
CONFIG_DIR = Path(user_config_dir("screenshot-tool"))
DEFAULT_CONFIG_PATH = CONFIG_DIR / "config.yaml"


@dataclass
class Config:
    """Screenshot tool configuration."""

    # Binary paths
    wayland_capture: str = "wayland-capture"

    # Output settings
    data_dir: Path = field(default_factory=lambda: Path(user_data_dir("screenshot-tool")))
    cache_dir: Path = field(default_factory=lambda: Path(user_cache_dir("screenshot-tool")))
    output_dir: Path = field(default_factory=lambda: Path.home() / "Pictures" / "screenshots")
    default_format: str = "png"
    default_quality: int = 90

    # Behavior
    double_tap_ms: int = 500
    enable_sound: bool = True
    enable_notification: bool = True
    enable_clipboard: bool = True

    # Paths
    lock_file: Path = field(default_factory=lambda: Path("/tmp/screenshot-tool.lock"))
    double_tap_file: Path = field(default_factory=lambda: Path("/tmp/screenshot-tool.doubletap"))

    # Silent mode output (for scripting)
    silent_output_dir: Path = field(default_factory=lambda: Path("/tmp"))

    # Hooks
    hooks_dir: Optional[Path] = field(default_factory=lambda: CONFIG_DIR / "hooks")

    def __post_init__(self):
        # Convert string paths to Path objects
        if isinstance(self.data_dir, str):
            self.data_dir = Path(self.data_dir)
        if isinstance(self.cache_dir, str):
            self.cache_dir = Path(self.cache_dir)
        if isinstance(self.output_dir, str):
            self.output_dir = Path(self.output_dir)
        if isinstance(self.lock_file, str):
            self.lock_file = Path(self.lock_file)
        if isinstance(self.double_tap_file, str):
            self.double_tap_file = Path(self.double_tap_file)
        if isinstance(self.silent_output_dir, str):
            self.silent_output_dir = Path(self.silent_output_dir)
        if isinstance(self.hooks_dir, str):
            self.hooks_dir = Path(self.hooks_dir)


DEFAULT_FORMATS = {"png", "jpg", "jpeg", "webp"}
PATH_KEYS = {
    "data_dir",
    "cache_dir",
    "output_dir",
    "lock_file",
    "double_tap_file",
    "silent_output_dir",
    "hooks_dir",
}


def _env(name: str) -> Optional[str]:
    return os.environ.get(f"{ENV_PREFIX}_{name}")


def _config_path_from_env() -> Optional[Path]:
    value = _env("CONFIG") or _env("CONFIG_PATH")
    if value:
        return Path(value).expanduser()
    return None


def _load_config_file(path: Path, strict: bool = False) -> dict:
    if not path.exists():
        return {}
    try:
        data = yaml.safe_load(path.read_text()) or {}
    except Exception as exc:
        if strict:
            raise ValueError(f"Failed to parse config file {path}: {exc}")
        return {}

    if not isinstance(data, dict):
        if strict:
            raise ValueError(f"Config file {path} must be a mapping")
        return {}

    return data


def _expand_path(value: Any) -> Any:
    if value is None:
        return value
    return str(Path(value).expanduser())


def config_defaults() -> dict:
    return {
        "wayland_capture": "wayland-capture",
        "data_dir": str(Path(user_data_dir("screenshot-tool"))),
        "cache_dir": str(Path(user_cache_dir("screenshot-tool"))),
        "output_dir": str(Path.home() / "Pictures" / "screenshots"),
        "default_format": "png",
        "default_quality": 90,
        "double_tap_ms": 500,
        "enable_sound": True,
        "enable_notification": True,
        "enable_clipboard": True,
        "lock_file": "/tmp/screenshot-tool.lock",
        "double_tap_file": "/tmp/screenshot-tool.doubletap",
        "silent_output_dir": "/tmp",
        "hooks_dir": str(CONFIG_DIR / "hooks"),
    }


def _load_env_overrides() -> dict:
    config: dict[str, Any] = {}

    mapping = {
        "WAYLAND_CAPTURE": "wayland_capture",
        "DATA_DIR": "data_dir",
        "CACHE_DIR": "cache_dir",
        "OUTPUT_DIR": "output_dir",
        "DEFAULT_FORMAT": "default_format",
        "DEFAULT_QUALITY": "default_quality",
        "DOUBLE_TAP_MS": "double_tap_ms",
        "LOCK_FILE": "lock_file",
        "DOUBLE_TAP_FILE": "double_tap_file",
        "SILENT_OUTPUT_DIR": "silent_output_dir",
        "HOOKS_DIR": "hooks_dir",
    }

    for env_name, key in mapping.items():
        value = _env(env_name)
        if value is None:
            continue
        if key in {"output_dir", "lock_file", "double_tap_file", "silent_output_dir", "hooks_dir"}:
            config[key] = _expand_path(value)
        elif key in {"data_dir", "cache_dir"}:
            config[key] = _expand_path(value)
        elif key in {"double_tap_ms", "default_quality"}:
            try:
                config[key] = int(value)
            except ValueError:
                continue
        else:
            config[key] = value

    for env_name, key in [
        ("ENABLE_SOUND", "enable_sound"),
        ("ENABLE_NOTIFICATION", "enable_notification"),
        ("ENABLE_CLIPBOARD", "enable_clipboard"),
    ]:
        value = _env(env_name)
        if value is None:
            continue
        config[key] = value.lower() in ("true", "1", "yes", "on")

    return config


def resolve_config_path(config_path: Optional[Path] = None) -> Path:
    return config_path or _config_path_from_env() or DEFAULT_CONFIG_PATH


def load_config(
    config_path: Optional[Path] = None,
    overrides: Optional[dict] = None,
    strict: bool = False,
) -> Config:
    """Load configuration from all sources."""
    resolved_path = resolve_config_path(config_path)

    config_dict = config_defaults()
    file_config = _load_config_file(resolved_path, strict=strict)
    config_dict.update(file_config)
    config_dict.update(_load_env_overrides())

    if overrides:
        for key, value in overrides.items():
            if value is not None:
                config_dict[key] = value

    for key in PATH_KEYS:
        if key in config_dict and config_dict[key] is not None:
            config_dict[key] = _expand_path(config_dict[key])

    return Config(**config_dict)


# Global config instance (lazy loaded)
_config: Optional[Config] = None


def get_config() -> Config:
    """Get the global configuration instance."""
    global _config
    if _config is None:
        _config = load_config()
    return _config


def config_schema() -> dict:
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "type": "object",
        "properties": {
            "wayland_capture": {"type": "string"},
            "data_dir": {"type": "string"},
            "cache_dir": {"type": "string"},
            "output_dir": {"type": "string"},
            "default_format": {"type": "string", "enum": sorted(DEFAULT_FORMATS)},
            "default_quality": {"type": "integer", "minimum": 1, "maximum": 100},
            "double_tap_ms": {"type": "integer", "minimum": 0},
            "enable_sound": {"type": "boolean"},
            "enable_notification": {"type": "boolean"},
            "enable_clipboard": {"type": "boolean"},
            "lock_file": {"type": "string"},
            "double_tap_file": {"type": "string"},
            "silent_output_dir": {"type": "string"},
            "hooks_dir": {"type": ["string", "null"]},
        },
        "additionalProperties": False,
    }


def _is_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def validate_config_dict(data: Any) -> list[str]:
    errors: list[str] = []
    if not isinstance(data, dict):
        return ["Config must be a mapping/object"]

    schema = config_schema()
    props = schema.get("properties", {})
    allowed_keys = set(props.keys())

    for key in data.keys():
        if key not in allowed_keys:
            errors.append(f"Unknown config key: {key}")

    def check_type(key: str, value: Any, expected: str) -> None:
        if expected == "string" and not isinstance(value, str):
            errors.append(f"{key} must be a string")
        elif expected == "integer" and not _is_int(value):
            errors.append(f"{key} must be an integer")
        elif expected == "boolean" and not isinstance(value, bool):
            errors.append(f"{key} must be a boolean")

    for key, value in data.items():
        if key not in props:
            continue
        spec = props[key]
        expected = spec.get("type")
        if isinstance(expected, list):
            if value is None and "null" in expected:
                continue
            if "string" in expected and isinstance(value, str):
                continue
            errors.append(f"{key} must be one of types: {', '.join(expected)}")
            continue
        if isinstance(expected, str):
            check_type(key, value, expected)

        if key == "default_format" and value not in DEFAULT_FORMATS:
            errors.append(f"default_format must be one of: {', '.join(sorted(DEFAULT_FORMATS))}")
        if key == "default_quality" and _is_int(value):
            if value < 1 or value > 100:
                errors.append("default_quality must be between 1 and 100")
        if key == "double_tap_ms" and _is_int(value) and value < 0:
            errors.append("double_tap_ms must be >= 0")

    return errors


def validate_config_file(config_path: Optional[Path] = None) -> list[str]:
    path = resolve_config_path(config_path)
    if not path.exists():
        return []
    data = _load_config_file(path, strict=True)
    return validate_config_dict(data)


def config_to_dict(config: Config) -> dict:
    def _format(value: Any) -> Any:
        if isinstance(value, Path):
            return str(value)
        return value

    return {
        "wayland_capture": config.wayland_capture,
        "data_dir": _format(config.data_dir),
        "cache_dir": _format(config.cache_dir),
        "output_dir": _format(config.output_dir),
        "default_format": config.default_format,
        "default_quality": config.default_quality,
        "double_tap_ms": config.double_tap_ms,
        "enable_sound": config.enable_sound,
        "enable_notification": config.enable_notification,
        "enable_clipboard": config.enable_clipboard,
        "lock_file": _format(config.lock_file),
        "double_tap_file": _format(config.double_tap_file),
        "silent_output_dir": _format(config.silent_output_dir),
        "hooks_dir": _format(config.hooks_dir) if config.hooks_dir else None,
    }
