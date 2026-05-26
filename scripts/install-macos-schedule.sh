#!/usr/bin/env bash
# 安装 macOS launchd 定时任务（工作日 06:30）
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PLIST_SRC="${ROOT_DIR}/scripts/com.us-industry-strength.daily.plist"
PLIST_DST="${HOME}/Library/LaunchAgents/com.us-industry-strength.daily.plist"
chmod +x "${ROOT_DIR}/scripts/scheduled_daily.sh"
chmod +x "${ROOT_DIR}/scripts/sync_breadth.py" 2>/dev/null || true
chmod +x "${ROOT_DIR}/scripts/precompute_daily.py" 2>/dev/null || true

sed "s|__PROJECT_ROOT__|${ROOT_DIR}|g" "$PLIST_SRC" >"$PLIST_DST"
launchctl unload "$PLIST_DST" 2>/dev/null || true
launchctl load "$PLIST_DST"
echo "已安装: $PLIST_DST"
echo "日志: ${ROOT_DIR}/logs/scheduled-YYYYMMDD.log"
echo "卸载: launchctl unload $PLIST_DST && rm $PLIST_DST"
