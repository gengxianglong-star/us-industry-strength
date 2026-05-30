#!/usr/bin/env bash
# 一键安装全自动：登录自启 Web 服务 + 工作日 06:30 备份 Daily（双保险）
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LAUNCH_AGENTS="${HOME}/Library/LaunchAgents"
mkdir -p "${ROOT_DIR}/logs" "${LAUNCH_AGENTS}"

chmod +x "${ROOT_DIR}/run.sh" 2>/dev/null || true
chmod +x "${ROOT_DIR}/scripts/scheduled_daily.sh" 2>/dev/null || true
chmod +x "${ROOT_DIR}/scripts/precompute_daily.py" 2>/dev/null || true

if [ ! -d "${ROOT_DIR}/.venv" ]; then
  python3 -m venv "${ROOT_DIR}/.venv"
fi
# shellcheck disable=SC1091
source "${ROOT_DIR}/.venv/bin/activate"
python -m pip install --upgrade pip -q
pip install -r "${ROOT_DIR}/requirements.txt" -q

install_plist() {
  local src="$1"
  local label="$2"
  local dst="${LAUNCH_AGENTS}/${label}.plist"
  sed "s|__PROJECT_ROOT__|${ROOT_DIR}|g" "${src}" >"${dst}"
  launchctl bootout "gui/$(id -u)" "${dst}" 2>/dev/null || launchctl unload "${dst}" 2>/dev/null || true
  launchctl bootstrap "gui/$(id -u)" "${dst}" 2>/dev/null || launchctl load "${dst}"
  echo "已安装: ${dst}"
}

if [[ "$(uname -s)" != "Darwin" ]]; then
  echo "非 macOS：请保持 run.sh serve 常驻（或配置 systemd）。服务端内置调度会在进程运行时自动 Daily。"
  exit 0
fi

install_plist "${ROOT_DIR}/scripts/com.us-industry-strength.server.plist" "com.us-industry-strength.server"
install_plist "${ROOT_DIR}/scripts/com.us-industry-strength.daily.plist" "com.us-industry-strength.daily"

echo ""
echo "全自动已就绪："
echo "  - Web 服务：登录自启，崩溃自动重启 → http://127.0.0.1:8080"
echo "  - 内置调度：启动补跑 + 工作日 06:30 + 失败每 20 分钟重试"
echo "  - 备份 cron：launchd daily 任务（服务离线时仍更新）"
echo "  - 日志：${ROOT_DIR}/logs/"
