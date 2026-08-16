from screenshot_tool.cli import _request_values, create_argument_parser


def test_default_request_is_interactive() -> None:
    args = create_argument_parser().parse_args([])
    values = {key: value.unpack() for key, value in _request_values(args).items()}
    assert values["mode"] == "interactive"


def test_noninteractive_options_cross_dbus_boundary() -> None:
    args = create_argument_parser().parse_args(
        [
            "--region",
            "1,2,30,40",
            "--silent",
            "--format",
            "webp",
            "--no-clipboard",
        ]
    )
    values = {key: value.unpack() for key, value in _request_values(args).items()}
    assert values == {
        "mode": "region",
        "region": "1,2,30,40",
        "silent": True,
        "format": "webp",
        "clipboard": False,
        "delay_ms": 0,
    }
