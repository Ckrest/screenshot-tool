"""Configuration management for Screenshot Tool.

Configuration is loaded from (highest priority first):
1. CLI arguments (passed directly to functions)
2. Environment variables (SCREENSHOT_*)
3. Settings Hub (if available)
4. Config file (~/.config/screenshot-tool/config.yaml)
5. Built-in defaults
"""

import os
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import yaml


def _load_settings_hub() -> dict:
    """Load settings from Settings Hub if available.

    Settings Hub stores user preferences in a central location.
    This is an optional integration - if unavailable, returns empty dict.
    """
    try:
        # Settings Hub stores settings at ~/.config/settings-hub/settings/<package>.yaml
        settings_path = Path.home() / ".config" / "settings-hub" / "settings" / "screenshot-tool.yaml"
        if settings_path.exists():
            with open(settings_path) as f:
                return yaml.safe_load(f) or {}
    except Exception:
        pass
    return {}


@dataclass
class Config:
    """Screenshot tool configuration."""

    # Binary paths
    wayland_capture: str = "wayland-capture"

    # Output settings
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

    # Silent mode output (for MCP/scripting)
    silent_output_dir: Path = field(default_factory=lambda: Path("/tmp"))

    def __post_init__(self):
        # Convert string paths to Path objects
        if isinstance(self.output_dir, str):
            self.output_dir = Path(self.output_dir)
        if isinstance(self.lock_file, str):
            self.lock_file = Path(self.lock_file)
        if isinstance(self.double_tap_file, str):
            self.double_tap_file = Path(self.double_tap_file)
        if isinstance(self.silent_output_dir, str):
            self.silent_output_dir = Path(self.silent_output_dir)


def _load_config_file() -> dict:
    """Load configuration from YAML file if it exists."""
    config_path = Path.home() / ".config" / "screenshot-tool" / "config.yaml"
    if config_path.exists():
        try:
            with open(config_path) as f:
                return yaml.safe_load(f) or {}
        except Exception:
            pass
    return {}


def _get_env(name: str, default: Optional[str] = None) -> Optional[str]:
    """Get environment variable with SCREENSHOT_ prefix."""
    return os.environ.get(f"SCREENSHOT_{name}", default)


def load_config() -> Config:
    """Load configuration from all sources.

    Priority (highest to lowest):
    1. Environment variables (SCREENSHOT_*)
    2. Settings Hub (if available)
    3. Config file (~/.config/screenshot-tool/config.yaml)
    4. Built-in defaults
    """
    # Start with defaults
    config_dict = {}

    # Load from config file (lowest priority)
    file_config = _load_config_file()
    config_dict.update(file_config)

    # Load from Settings Hub (overrides config file)
    hub_config = _load_settings_hub()
    config_dict.update(hub_config)

    # Override with environment variables
    env_mappings = {
        "WAYLAND_CAPTURE": "wayland_capture",
        "OUTPUT_DIR": "output_dir",
        "DEFAULT_FORMAT": "default_format",
        "DOUBLE_TAP_MS": "double_tap_ms",
        "LOCK_FILE": "lock_file",
    }

    for env_name, config_key in env_mappings.items():
        value = _get_env(env_name)
        if value is not None:
            # Convert to appropriate type
            if config_key == "double_tap_ms":
                config_dict[config_key] = int(value)
            elif config_key in ("output_dir", "lock_file", "double_tap_file", "silent_output_dir"):
                config_dict[config_key] = Path(value)
            else:
                config_dict[config_key] = value

    # Boolean environment variables
    for env_name, config_key in [
        ("ENABLE_SOUND", "enable_sound"),
        ("ENABLE_NOTIFICATION", "enable_notification"),
        ("ENABLE_CLIPBOARD", "enable_clipboard"),
    ]:
        value = _get_env(env_name)
        if value is not None:
            config_dict[config_key] = value.lower() in ("true", "1", "yes")

    # Find wayland-capture binary if not explicitly set
    if "wayland_capture" not in config_dict:
        # Check common locations
        search_paths = [
            Path.home() / "Systems" / "desktop" / "wayland-window-capture" / "wayland-capture",
            Path("/usr/local/bin/wayland-capture"),
            Path("/usr/bin/wayland-capture"),
        ]
        for path in search_paths:
            if path.exists() and os.access(path, os.X_OK):
                config_dict["wayland_capture"] = str(path)
                break
        else:
            # Fall back to searching PATH
            found = shutil.which("wayland-capture")
            if found:
                config_dict["wayland_capture"] = found

    return Config(**config_dict)


# Global config instance (lazy loaded)
_config: Optional[Config] = None


def get_config() -> Config:
    """Get the global configuration instance."""
    global _config
    if _config is None:
        _config = load_config()
    return _config
