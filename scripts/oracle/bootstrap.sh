#!/usr/bin/env bash
# One-time setup on a fresh Ubuntu ARM/x64 VM (Oracle Cloud Always Free).
set -euo pipefail

REPO_URL="${REPO_URL:-https://github.com/gengxianglong-star/us-industry-strength.git}"
INSTALL_DIR="${INSTALL_DIR:-$HOME/us-industry-strength}"

echo "==> Installing system packages…"
export DEBIAN_FRONTEND=noninteractive
sudo apt-get update -qq
sudo apt-get install -y -qq \
  git curl ca-certificates zip unzip \
  python3 python3-venv python3-pip \
  build-essential libffi-dev

if ! command -v gh >/dev/null 2>&1; then
  echo "==> Installing GitHub CLI…"
  curl -fsSL https://cli.github.com/packages/githubcli-archive-keyring.gpg | sudo dd of=/usr/share/keyrings/githubcli-archive-keyring.gpg 2>/dev/null
  echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/githubcli-archive-keyring.gpg] https://cli.github.com/packages stable main" | sudo tee /etc/apt/sources.list.d/github-cli.list >/dev/null
  sudo apt-get update -qq
  sudo apt-get install -y -qq gh
fi

if [ ! -d "$INSTALL_DIR/.git" ]; then
  echo "==> Cloning repository…"
  git clone "$REPO_URL" "$INSTALL_DIR"
else
  echo "==> Updating repository…"
  git -C "$INSTALL_DIR" pull --ff-only
fi

cd "$INSTALL_DIR"
chmod +x run.sh scripts/*.sh scripts/oracle/*.sh 2>/dev/null || true

echo "==> Python virtualenv + dependencies…"
python3 -m venv .venv
# shellcheck disable=SC1091
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt

mkdir -p logs data secrets

if [ ! -f .oracle.env ]; then
  cp scripts/oracle/env.example .oracle.env
  chmod 600 .oracle.env
  echo ""
  echo "IMPORTANT: Edit $INSTALL_DIR/.oracle.env and set GITHUB_TOKEN"
  echo "  nano $INSTALL_DIR/.oracle.env"
fi

echo "==> Installing systemd timer (06:30 Asia/Shanghai, Mon–Fri)…"
bash scripts/oracle/install-systemd.sh

echo ""
echo "Bootstrap complete."
echo "Next steps:"
echo "  1. nano $INSTALL_DIR/.oracle.env   # set GITHUB_TOKEN"
echo "  2. bash scripts/oracle/daily_pipeline.sh   # test once manually"
echo "  3. systemctl list-timers us-industry-daily.timer"
