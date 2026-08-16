from pathlib import Path

import yaml


def test_actions_launch_installed_command() -> None:
    root = Path(__file__).resolve().parents[1]
    payload = yaml.safe_load(
        (root / "pkg" / "wayfire-keybindings" / "actions.yaml").read_text()
    )

    commands = [action["runner"]["command"] for action in payload["actions"]]

    assert commands
    assert all(command.startswith("screenshot") for command in commands)
    assert all("python" not in command for command in commands)
