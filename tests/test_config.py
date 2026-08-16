from pathlib import Path

from screenshot_tool import config


def test_runtime_defaults_use_xdg_runtime_dir(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path))
    assert (
        Path(config.config_defaults()["silent_output_dir"])
        == tmp_path / "screenshot-tool" / "captures"
    )


def test_old_runtime_keys_are_ignored_during_load(tmp_path) -> None:
    path = tmp_path / "config.yaml"
    path.write_text(
        "lock_file: /tmp/old\ncapture_helper: /old/helper\ndefault_quality: 81\n"
    )
    loaded = config.load_config(path)
    assert loaded.default_quality == 81
    assert not hasattr(loaded, "lock_file")
    assert not hasattr(loaded, "capture_helper")


def test_validation_rejects_old_keys(tmp_path) -> None:
    path = tmp_path / "config.yaml"
    path.write_text("lock_file: /tmp/old\n")
    assert config.validate_config_file(path) == ["Unknown configuration key: lock_file"]
