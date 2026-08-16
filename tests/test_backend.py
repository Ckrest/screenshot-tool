import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from screenshot_tool.backend import CaptureError, WaylandCaptureBackend
from screenshot_tool.config import Config


def metadata(**updates):
    value = {
        "schema": "wayland-capture/frame@1",
        "type": "raw",
        "width": 2,
        "height": 2,
        "stride": 8,
        "pixel_format": "rgba8888",
        "alpha": "straight",
        "transform": "normal",
        "cursor_included": False,
        "source": {
            "type": "output",
            "name": "DP-3",
            "logical_origin": {"x": 0, "y": 0},
            "canvas_scale": 1.0,
            "outputs": [
                {
                    "name": "DP-3",
                    "logical_x": 0,
                    "logical_y": 0,
                    "logical_width": 2,
                    "logical_height": 2,
                    "buffer_width": 2,
                    "buffer_height": 2,
                    "scale": 1.0,
                    "transform": "normal",
                    "frame_x": 0,
                    "frame_y": 0,
                    "frame_width": 2,
                    "frame_height": 2,
                }
            ],
        },
    }
    value.update(updates)
    return value


@patch("screenshot_tool.backend.subprocess.run")
def test_desktop_capture_uses_raw_contract_without_cursor(
    mock_run, monkeypatch, tmp_path
) -> None:
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path))

    def run(command, **_kwargs):
        path = command[command.index("--output-file") + 1]
        Path(path).write_bytes(b"\0" * 16)
        return MagicMock(returncode=0, stdout=json.dumps(metadata()), stderr="")

    mock_run.side_effect = run
    frame = WaylandCaptureBackend(Config()).capture_desktop("DP-3")
    command = mock_run.call_args.args[0]
    assert command[:3] == ["wayland-capture", "--output", "DP-3"]
    assert ["--format", "raw"] == command[
        command.index("--format") : command.index("--format") + 2
    ]
    assert frame.output_name == "DP-3"
    assert frame.logical_origin == (0, 0)
    assert frame.canvas_scale == 1.0
    assert frame.outputs[0].name == "DP-3"


@patch("screenshot_tool.backend.subprocess.run")
def test_window_capture_uses_exact_identifier(mock_run, monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path))

    def run(command, **_kwargs):
        path = command[command.index("--output-file") + 1]
        Path(path).write_bytes(b"\0" * 16)
        return MagicMock(returncode=0, stdout=json.dumps(metadata()), stderr="")

    mock_run.side_effect = run
    WaylandCaptureBackend(Config()).capture_window("opaque-id-1")
    command = mock_run.call_args.args[0]
    assert command[:3] == ["wayland-capture", "--window-id", "opaque-id-1"]


def test_schema_and_cursor_are_validated(tmp_path) -> None:
    path = tmp_path / "raw"
    path.write_bytes(b"\0" * 16)
    with pytest.raises(CaptureError, match="included the cursor"):
        WaylandCaptureBackend._load_frame(path, metadata(cursor_included=True))
    with pytest.raises(CaptureError, match="schema"):
        WaylandCaptureBackend._load_frame(path, metadata(schema="other"))


def test_payload_size_is_validated(tmp_path) -> None:
    path = tmp_path / "raw"
    path.write_bytes(b"too short")
    with pytest.raises(CaptureError, match="dimensions"):
        WaylandCaptureBackend._load_frame(path, metadata())
