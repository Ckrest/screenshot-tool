#!/usr/bin/env bash
set -euo pipefail

SCRIPT_PATH="$(readlink -f "$0")"
ROOT_DIR="$(cd "$(dirname "$SCRIPT_PATH")" && pwd)"
CONFIG_HOME="${XDG_CONFIG_HOME:-$HOME/.config}"
DATA_HOME="${XDG_DATA_HOME:-$HOME/.local/share}"

python3 -m pip install --user --editable "$ROOT_DIR" --break-system-packages
mkdir -p \
  "$CONFIG_HOME/screenshot-tool" \
  "$CONFIG_HOME/systemd/user" \
  "$CONFIG_HOME/wayfire-keybindings/actions.d" \
  "$DATA_HOME/applications" \
  "$DATA_HOME/settings-hub/tile-sets"
if [[ ! -f "$CONFIG_HOME/screenshot-tool/config.yaml" ]]; then
  install -m 600 "$ROOT_DIR/config.example.yaml" "$CONFIG_HOME/screenshot-tool/config.yaml"
fi
ln -sfn "$ROOT_DIR/pkg/systemd/screenshot-tool.service" \
  "$CONFIG_HOME/systemd/user/screenshot-tool.service"
ln -sfn "$ROOT_DIR/pkg/applications/org.nick.ScreenshotTool.desktop" \
  "$DATA_HOME/applications/org.nick.ScreenshotTool.desktop"
ln -sfn "$ROOT_DIR/pkg/wayfire-keybindings/actions.yaml" \
  "$CONFIG_HOME/wayfire-keybindings/actions.d/screenshot-tool.yaml"
ln -sfn "$ROOT_DIR/integrations/settings-hub/tile-sets/screenshot-tool.yaml" \
  "$DATA_HOME/settings-hub/tile-sets/screenshot-tool.yaml"

systemctl --user daemon-reload
systemctl --user enable screenshot-tool.service
systemctl --user restart screenshot-tool.service
screenshot --version
echo "Installed and started Screenshot Tool 3 service."
