#!/usr/bin/env bash
set -euo pipefail

SCRIPT_PATH="$(readlink -f "$0")"
ROOT_DIR="$(cd "$(dirname "$SCRIPT_PATH")" && pwd)"
CONFIG_HOME="${XDG_CONFIG_HOME:-$HOME/.config}"
DATA_HOME="${XDG_DATA_HOME:-$HOME/.local/share}"

systemctl --user disable --now screenshot-tool.service 2>/dev/null || true
for owned in \
  "$CONFIG_HOME/systemd/user/screenshot-tool.service:$ROOT_DIR/pkg/systemd/screenshot-tool.service" \
  "$CONFIG_HOME/wayfire-keybindings/actions.d/screenshot-tool.yaml:$ROOT_DIR/pkg/wayfire-keybindings/actions.yaml" \
  "$DATA_HOME/applications/org.nick.ScreenshotTool.desktop:$ROOT_DIR/pkg/applications/org.nick.ScreenshotTool.desktop" \
  "$DATA_HOME/settings-hub/tile-sets/screenshot-tool.yaml:$ROOT_DIR/integrations/settings-hub/tile-sets/screenshot-tool.yaml"; do
  link="${owned%%:*}"
  source="${owned#*:}"
  if [[ -L "$link" ]] && [[ "$(readlink -f "$link")" == "$source" ]]; then rm "$link"; fi
done
systemctl --user daemon-reload
python3 -m pip uninstall -y screenshot-tool --break-system-packages
echo "Uninstalled Screenshot Tool integrations; configuration and screenshots were retained."
