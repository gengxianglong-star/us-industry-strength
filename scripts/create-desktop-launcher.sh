#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DESKTOP_DIR="${HOME}/Desktop"
LAUNCHER_PATH="${DESKTOP_DIR}/US-Industry-Strength.command"

if [ ! -d "${DESKTOP_DIR}" ]; then
  echo "未找到桌面目录: ${DESKTOP_DIR}"
  exit 1
fi

cat > "${LAUNCHER_PATH}" <<EOF
#!/usr/bin/env bash
cd "${ROOT_DIR}"
./run.sh
EOF

chmod +x "${LAUNCHER_PATH}"

echo "已创建桌面启动器:"
echo "  ${LAUNCHER_PATH}"
echo "以后双击它即可启动网站。"
