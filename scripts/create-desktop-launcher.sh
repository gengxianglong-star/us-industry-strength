#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DESKTOP_DIR="${HOME}/Desktop"
APP_NAME="Open US Industry Strength.app"
APP_PATH="${DESKTOP_DIR}/${APP_NAME}"
OPEN_SCRIPT="${ROOT_DIR}/scripts/open-dashboard.sh"

if [ ! -d "${DESKTOP_DIR}" ]; then
  echo "未找到桌面目录: ${DESKTOP_DIR}"
  exit 1
fi

chmod +x "${ROOT_DIR}/run.sh" 2>/dev/null || true
chmod +x "${OPEN_SCRIPT}"

APPLESCRIPT="do shell script \"bash '${OPEN_SCRIPT}'\" with prompt \"Starting dashboard…\""

if command -v osacompile >/dev/null 2>&1; then
  rm -rf "${APP_PATH}"
  osacompile -o "${APP_PATH}" -e "${APPLESCRIPT}"
  echo "已创建桌面启动器（双击即可：自动启动服务 + 打开 Edge）："
  echo "  ${APP_PATH}"
else
  LEGACY="${DESKTOP_DIR}/US-Industry-Strength.command"
  cat > "${LEGACY}" <<EOF
#!/usr/bin/env bash
exec bash "${OPEN_SCRIPT}"
EOF
  chmod +x "${LEGACY}"
  echo "已创建桌面启动器："
  echo "  ${LEGACY}"
fi

echo ""
echo "建议：把 ${APP_NAME} 固定到 Dock，以后不用开终端。"
