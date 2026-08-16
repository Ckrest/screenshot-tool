from datetime import datetime, timezone

import gi

gi.require_version("GdkPixbuf", "2.0")
from gi.repository import GdkPixbuf
from screenshot_tool.config import Config
from screenshot_tool.models import CaptureRequest, RawFrame
from screenshot_tool.output import (
    MIME_TYPES,
    options_for_request,
    output_path,
    save_frame,
)


def test_context_filename_and_collision(tmp_path) -> None:
    config = Config(output_dir=tmp_path)
    options = options_for_request(CaptureRequest(mode="fullscreen"), config)
    now = datetime(2026, 8, 15, 14, 32, 8, tzinfo=timezone.utc)
    first = output_path(options, config, "fullscreen", now=now)
    assert first.name == "Screenshot_2026-08-15_14-32-08_Fullscreen.png"
    first.touch()
    assert output_path(options, config, "fullscreen", now=now).name.endswith(
        "Fullscreen_2.png"
    )


def test_silent_disables_desktop_side_effects(tmp_path) -> None:
    config = Config(silent_output_dir=tmp_path)
    options = options_for_request(
        CaptureRequest(mode="fullscreen", silent=True), config
    )
    assert not options.clipboard and not options.notification and not options.sound


def test_explicit_path_extension_selects_format(tmp_path) -> None:
    config = Config(output_dir=tmp_path, default_format="png")
    options = options_for_request(
        CaptureRequest(mode="fullscreen", output_path=tmp_path / "shot.webp"), config
    )
    assert options.output_format == "webp"


def test_frame_is_encoded_directly_to_final_file(tmp_path) -> None:
    config = Config(output_dir=tmp_path)
    request = CaptureRequest(mode="region", output_path=tmp_path / "result.png")
    options = options_for_request(request, config)
    frame = RawFrame(2, 2, 8, bytes([255, 0, 0, 255] * 4))
    result = save_frame(frame, options, config, "region")
    loaded = GdkPixbuf.Pixbuf.new_from_file(str(result.path))
    assert (loaded.get_width(), loaded.get_height()) == (2, 2)
    assert not list(tmp_path.glob("*.part"))
    assert MIME_TYPES[options.output_format] == "image/png"
