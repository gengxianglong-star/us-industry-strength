# Oracle Cloud — full automation (no Mac required)

Run the **same daily pipeline as your Mac** on Oracle **Always Free** VM, then auto-publish to GitHub Pages.

```text
Oracle VM (free)
  Mon–Fri 06:30 Beijing
    → Finviz + screener + sync RS + watchlist + breadth
    → export JSON → GitHub Release (dashboard-data.zip)
    → trigger Pages workflow

GitHub Pages
  → https://gengxianglong-star.github.io/us-industry-strength/strong

Your Mac
  → can stay off
```

You do **not** buy hardware. You only need a free Oracle account + free GitHub account.

---

## Part 1 — Oracle account & VM (one time, ~30 min)

### 1. Register

1. Open https://www.oracle.com/cloud/free/
2. Sign up (credit card is for **identity verification** — stay in **Always Free** resources to avoid charges)
3. Choose home region close to you (e.g. ap-tokyo-1, ap-seoul-1)

### 2. Create an ARM VM (Always Free)

1. Console → **Compute** → **Instances** → **Create instance**
2. Name: `us-industry-strength`
3. **Image**: Ubuntu 22.04 or 24.04 (aarch64)
4. **Shape**: **Ampere A1** — Always Free-eligible  
   - OCPUs: **4**, Memory: **24 GB** (max free tier)
5. **Networking**: use default VCN; assign a **public IPv4**
6. **SSH keys**: paste your Mac public key (`~/.ssh/id_ed25519.pub`)  
   - If missing: `ssh-keygen -t ed25519 -N "" -f ~/.ssh/id_ed25519`
7. **Boot volume**: 50–100 GB (within free allowance)
8. Create

Note the **public IP** (e.g. `123.45.67.89`).

### 3. Open SSH (if needed)

Default Ubuntu image allows SSH (port 22) from anywhere on Oracle’s default security list.  
If SSH fails: Networking → VCN → Security List → allow ingress TCP 22 from your IP.

### 4. SSH into the VM

```bash
ssh ubuntu@YOUR_VM_PUBLIC_IP
```

(User may be `ubuntu` or `opc` depending on image — Oracle Ubuntu uses `ubuntu`.)

---

## Part 2 — Install the project on the VM

```bash
git clone https://github.com/gengxianglong-star/us-industry-strength.git
cd us-industry-strength
bash scripts/oracle/bootstrap.sh
```

This installs Python, `gh`, dependencies, and a **systemd timer** (Mon–Fri 06:30 Asia/Shanghai).

---

## Part 3 — GitHub token (required)

On your Mac or VM:

1. GitHub → **Settings** → **Developer settings** → **Personal access tokens**
2. Create token with:
   - **repo** (full) — for releases  
   - **workflow** — to trigger `pages.yml`
3. On the VM:

```bash
nano ~/us-industry-strength/.oracle.env
```

Set:

```bash
GITHUB_TOKEN=ghp_your_token_here
GITHUB_REPO=gengxianglong-star/us-industry-strength
```

Save. File is gitignored.

Verify:

```bash
cd ~/us-industry-strength
export $(grep -v '^#' .oracle.env | xargs)
gh auth status
```

---

## Part 4 — Test once manually

```bash
cd ~/us-industry-strength
bash scripts/oracle/daily_pipeline.sh
```

Takes **30–90 minutes** first time (RS + breadth). Watch log:

```bash
tail -f logs/oracle-daily-$(date +%Y%m%d).log
```

When done:

1. GitHub → **Actions** → **Publish read-only dashboard** should start
2. Hard refresh Pages: `/strong` and `/breadth`

---

## Part 5 — Optional improvements

### Seed database from Mac (faster first day)

On Mac:

```bash
scp /Users/gxl_s/Projects/us-industry-strength/data/industry_strength.db \
  ubuntu@YOUR_VM_IP:~/us-industry-strength/data/
```

### Finviz Cloudflare cookie

If screener fails on VM:

1. Export Netscape cookies from browser on Mac
2. `scp cookies.txt ubuntu@VM:~/us-industry-strength/secrets/finviz_cookies.txt`
3. Edit `config.yaml` on VM: `scraper.cookie_file: secrets/finviz_cookies.txt`

### Disable Mac launchd (avoid duplicate work)

On Mac:

```bash
launchctl bootout gui/$(id -u) ~/Library/LaunchAgents/com.us-industry-strength.daily.plist 2>/dev/null || true
```

---

## Operations cheat sheet

| Task | Command (on VM) |
|------|-----------------|
| Run daily now | `bash ~/us-industry-strength/scripts/oracle/daily_pipeline.sh` |
| Timer status | `systemctl list-timers us-industry-daily.timer` |
| Today’s log | `tail -f ~/us-industry-strength/logs/oracle-daily-$(date +%Y%m%d).log` |
| Update code | `cd ~/us-industry-strength && git pull && bash scripts/oracle/bootstrap.sh` |
| Publish only (no recompute) | `bash scripts/package_pages_data.sh && bash scripts/oracle/publish_pages.sh` |

---

## GitHub Pages settings

Ensure repo **Settings → Pages → Source: GitHub Actions** (same as before).

The VM triggers `pages.yml` with **skip_precompute=true** after uploading `dashboard-data.zip`.  
The scheduled GitHub cron is **disabled** when using Oracle — the VM owns the schedule.

---

## Cost

| Item | Cost |
|------|------|
| Oracle Always Free VM | $0 |
| GitHub public repo + Pages | $0 |
| Mac running | Not required |

Stay within Always Free shapes (Ampere A1, boot volume limits). Do not create paid shapes unless you intend to pay.

---

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| `gh: command not found` | Re-run `bash scripts/oracle/bootstrap.sh` |
| `GITHUB_TOKEN not set` | Edit `.oracle.env` |
| Workflow not triggered | Token needs `workflow` scope; repo must be public or token has access |
| Only 3 industries | Add Finviz cookie; check log for Cloudflare errors |
| Breadth history short | First run calls `ensure_breadth_history.py` (full sync if shallow) |
| Pages still old | Wait for Actions green tick; Cmd+Shift+R on site |

See also: [deploy-readonly-pages.md](deploy-readonly-pages.md)
