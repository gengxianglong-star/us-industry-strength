#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
USER_NAME="${SUDO_USER:-$(whoami)}"

SERVICE_SRC="$ROOT_DIR/scripts/oracle/us-industry-daily.service"
TIMER_SRC="$ROOT_DIR/scripts/oracle/us-industry-daily.timer"

sed "s|__PROJECT_ROOT__|$ROOT_DIR|g;s|__USER__|$USER_NAME|g" "$SERVICE_SRC" | sudo tee /etc/systemd/system/us-industry-daily.service >/dev/null
sudo cp "$TIMER_SRC" /etc/systemd/system/us-industry-daily.timer

sudo systemctl daemon-reload
sudo systemctl enable us-industry-daily.timer
sudo systemctl start us-industry-daily.timer

echo "Installed us-industry-daily.timer"
systemctl list-timers us-industry-daily.timer --no-pager || true
