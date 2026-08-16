"""Tests for screenshot_tool.window module."""

import json
from unittest.mock import MagicMock, patch

from screenshot_tool.window import (
    Window,
    enumerate_windows,
    find_window_at,
    find_window_by_app_id,
    find_window_in_list,
)


class TestEnumerateWindows:
    @staticmethod
    def _make_wayfire_windows():
        return [
            {
                "id": 11,
                "app_id": "brave-browser",
                "title": "YouTube - Brave",
                "x": 100,
                "y": 100,
                "width": 1400,
                "height": 900,
                "z_order": 0,
                "capture_identifier": "opaque-brave",
            },
            {
                "id": 3084,
                "app_id": "thunar",
                "title": "screenshots - Thunar",
                "x": 50,
                "y": 50,
                "width": 800,
                "height": 600,
                "z_order": 1,
                "capture_identifier": "opaque-thunar",
            },
            {
                "id": 2952,
                "app_id": "kitty",
                "title": "Terminal 1",
                "x": 200,
                "y": 200,
                "width": 700,
                "height": 500,
                "z_order": 2,
                "capture_identifier": "opaque-kitty-a",
            },
            {
                "id": 3055,
                "app_id": "kitty",
                "title": "Terminal 2",
                "x": 300,
                "y": 300,
                "width": 700,
                "height": 500,
                "z_order": 3,
                "capture_identifier": "opaque-kitty-b",
            },
        ]

    @staticmethod
    def _make_capture_list():
        return {
            "outputs": [],
            "windows": [
                {
                    "identifier": "opaque-brave",
                    "app_id": "brave-browser",
                    "title": "YouTube - Brave",
                },
                {
                    "identifier": "opaque-thunar",
                    "app_id": "thunar",
                    "title": "screenshots - Thunar",
                },
                {
                    "identifier": "opaque-kitty-a",
                    "app_id": "kitty",
                    "title": "Terminal",
                },
                {
                    "identifier": "opaque-kitty-b",
                    "app_id": "kitty",
                    "title": "Terminal",
                },
            ],
        }

    @patch("screenshot_tool.window.get_window_geometries")
    @patch("screenshot_tool.window.subprocess.run")
    def test_pairs_by_exact_identifier(self, mock_run, mock_wayfire):
        mock_wayfire.return_value = self._make_wayfire_windows()
        mock_run.return_value = MagicMock(
            returncode=0, stdout=json.dumps(self._make_capture_list())
        )

        windows = enumerate_windows()

        assert len(windows) == 4
        by_app = {w.app_id: w for w in windows}

        brave = by_app["brave-browser"]
        assert brave.capture_id == "opaque-brave"
        assert brave.view_id == 11

        thunar = by_app["thunar"]
        assert thunar.capture_id == "opaque-thunar"
        assert thunar.view_id == 3084

    @patch("screenshot_tool.window.get_window_geometries")
    @patch("screenshot_tool.window.subprocess.run")
    def test_pairs_duplicate_identical_windows_by_exact_identifier(
        self, mock_run, mock_wayfire
    ):
        mock_wayfire.return_value = self._make_wayfire_windows()
        mock_run.return_value = MagicMock(
            returncode=0, stdout=json.dumps(self._make_capture_list())
        )

        windows = enumerate_windows()

        kitties = [w for w in windows if w.app_id == "kitty"]
        assert len(kitties) == 2
        assert {w.view_id for w in kitties} == {2952, 3055}
        assert {w.capture_id for w in kitties} == {
            "opaque-kitty-a",
            "opaque-kitty-b",
        }

    @patch("screenshot_tool.window.get_window_geometries")
    @patch("screenshot_tool.window.subprocess.run")
    def test_missing_identifier_does_not_fall_back_to_title(
        self, mock_run, mock_wayfire
    ):
        wayfire_windows = self._make_wayfire_windows()
        wayfire_windows[0]["capture_identifier"] = ""
        mock_wayfire.return_value = wayfire_windows
        mock_run.return_value = MagicMock(
            returncode=0, stdout=json.dumps(self._make_capture_list())
        )

        windows = enumerate_windows()
        brave = next(w for w in windows if w.app_id == "brave-browser")
        assert brave.capture_id == ""

    @patch("screenshot_tool.window.get_window_geometries")
    @patch("screenshot_tool.window.subprocess.run")
    def test_window_without_capture_match_has_empty_capture_id(
        self, mock_run, mock_wayfire
    ):
        wayfire_windows = self._make_wayfire_windows()
        mock_wayfire.return_value = wayfire_windows
        capture_list = self._make_capture_list()
        # Remove brave from capture list.
        capture_list["windows"] = [
            w for w in capture_list["windows"] if w["identifier"] != "opaque-brave"
        ]
        mock_run.return_value = MagicMock(returncode=0, stdout=json.dumps(capture_list))

        windows = enumerate_windows()
        brave = next(w for w in windows if w.app_id == "brave-browser")
        assert brave.capture_id == ""
        assert brave.view_id == 11

    @patch("screenshot_tool.window.get_window_geometries")
    @patch("screenshot_tool.window.subprocess.run")
    def test_capture_failure_returns_wayfire_windows_only(self, mock_run, mock_wayfire):
        mock_wayfire.return_value = self._make_wayfire_windows()
        mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="error")

        windows = enumerate_windows()
        assert len(windows) == 4
        assert all(w.capture_id == "" for w in windows)


class TestFindWindowByAppId:
    @patch("screenshot_tool.window.enumerate_windows")
    def test_finds_frontmost_match(self, mock_enumerate):
        mock_enumerate.return_value = [
            Window("kitty", "opaque-b", "T2", 3055, 0, 0, 0, 0, z_order=1),
            Window("kitty", "opaque-a", "T1", 2952, 0, 0, 0, 0, z_order=0),
        ]

        found = find_window_by_app_id("kitty")
        assert found is not None
        assert found.view_id == 2952
        assert found.z_order == 0

    @patch("screenshot_tool.window.enumerate_windows")
    def test_returns_none_when_no_match(self, mock_enumerate):
        mock_enumerate.return_value = [
            Window("brave-browser", "", "", None, 0, 0, 0, 0),
        ]
        assert find_window_by_app_id("kitty") is None


class TestFindWindowAt:
    @patch("screenshot_tool.window.enumerate_windows")
    def test_finds_window_at_coordinates(self, mock_enumerate):
        mock_enumerate.return_value = [
            Window("bg", "", "", None, 0, 0, 1920, 1080, z_order=1),
            Window("front", "opaque-front", "", 1, 100, 100, 200, 200, z_order=0),
        ]

        found = find_window_at(150, 150)
        assert found is not None
        assert found.app_id == "front"

    @patch("screenshot_tool.window.enumerate_windows")
    def test_returns_none_outside(self, mock_enumerate):
        mock_enumerate.return_value = [
            Window("front", "opaque-front", "", 1, 100, 100, 200, 200, z_order=0),
        ]
        assert find_window_at(50, 50) is None

    def test_finds_window_in_existing_snapshot(self):
        windows = [
            Window("bg", "", "", None, 0, 0, 1920, 1080, z_order=1),
            Window("front", "opaque-front", "", 1, 100, 100, 200, 200, z_order=0),
        ]

        found = find_window_in_list(windows, 150, 150)

        assert found is not None
        assert found.app_id == "front"
