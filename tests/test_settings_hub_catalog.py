from pathlib import Path

import yaml


def test_catalog_exposes_clipboard_setting() -> None:
    root = Path(__file__).resolve().parents[1]
    payload = yaml.safe_load(
        (
            root
            / "integrations"
            / "settings-hub"
            / "tile-sets"
            / "screenshot-tool.yaml"
        ).read_text()
    )

    assert len(payload) == 1
    tile_set = payload[0]
    assert tile_set["schema_version"] == 5
    assert tile_set["package"] == "screenshot-tool"
    assert tile_set["config"] == {
        "file": "~/.config/screenshot-tool/config.yaml",
        "format": "yaml",
    }

    clipboard_tile = next(
        tile
        for tile in tile_set["tiles"]
        if tile["id"] == "screenshot-copy-to-clipboard"
    )
    assert clipboard_tile["type"] == "toggle"
    assert clipboard_tile["props"] == {
        "section_id": "$root",
        "key": "enable_clipboard",
    }

    assert {tile["props"]["key"] for tile in tile_set["tiles"]} == {
        "default_format",
        "enable_clipboard",
        "enable_notification",
        "enable_sound",
        "include_window_title",
    }
