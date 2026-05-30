# Read-only dashboard (GitHub Pages)

Publish a **read-only** Strong Industry + Breadth dashboard to GitHub Pages at zero cost.  
No server, no Cloudflare Tunnel — phone / Mac / Windows browsers load static HTML + JSON.

Live URL (after setup):

`https://<github-user>.github.io/us-industry-strength/strong`

## What you get

| Feature | Read-only Pages | Local `run.sh serve` |
|---------|-----------------|----------------------|
| Top 15 + watchlist charts | Yes | Yes |
| RS evidence tables | Yes | Yes |
| Breadth cockpit + charts | Yes | Yes |
| Edit config / save thresholds | No | Yes |
| Manual RS / breadth sync | No | Yes |
| Auto daily update | GitHub Actions cron | launchd / built-in scheduler |

## One-time GitHub setup

1. Push this repo to GitHub (`main` branch).
2. **Settings → Pages → Build and deployment → Source: GitHub Actions**.
3. (Optional) **Settings → Actions → General → Workflow permissions → Read and write**.

## How updates work

Workflow: [`.github/workflows/pages.yml`](../.github/workflows/pages.yml)

```text
Restore SQLite cache (Actions cache)
  → precompute_daily.py   (weekday ~06:30 Beijing + manual runs)
  → export_public_dashboard.py  → frontend/public/data/*.json
  → Vite build (VITE_READONLY=1)
  → deploy-pages
  → save SQLite cache
```

Schedule: **Mon–Fri 06:30 Asia/Shanghai** (via UTC cron).

Manual run: **Actions → Publish read-only dashboard → Run workflow**.

## Local preview (read-only mode)

```bash
python scripts/export_public_dashboard.py
cd frontend
VITE_READONLY=1 VITE_BASE=/us-industry-strength/ npm run build:pages
npx serve dist -p 5173
# open http://127.0.0.1:5173/us-industry-strength/strong
```

## Seeding data (first run)

The workflow keeps `data/industry_strength.db` in **Actions cache**. On the first run the cache is empty and `precompute_daily.py` must fetch Finviz / Yahoo / Stockbee from GitHub’s US runners.

If cloud scraping fails (Cloudflare, etc.):

### Recommended: publish from your Mac (full data)

Your Mac already has richer data (more industries + watchlist + breadth). Package and upload it:

```bash
# optional: backfill years of breadth history first
python scripts/sync_breadth.py --full

./scripts/package_pages_data.sh
gh release create dashboard-data dashboard-data.zip --title "Dashboard data" --notes "Local export" 2>/dev/null \
  || gh release upload dashboard-data dashboard-data.zip --clobber

# Actions → Publish read-only dashboard → Run workflow → check "Skip daily precompute"
```

The workflow loads `dashboard-data.zip` from the **`dashboard-data` release** and skips CI scraping.

**Practical tip:** keep the Mac pipeline as the “source of truth” for hard-to-scrape days; Pages is for **reading** the latest successful export.

## Static JSON files

Written to `frontend/public/data/` during CI:

| File | Replaces API |
|------|----------------|
| `snapshot.json` | `/api/snapshots/latest` |
| `rs.json` | `/api/rs/{date}` |
| `rs_watchlist.json` | watchlist-only RS |
| `automation.json` | `/api/automation/status` |
| `breadth.json` | `/api/breadth` |
| `breadth_config.json` | `/api/breadth/config` |
| `health.json` | `/api/health` |
| `meta.json` | export timestamp |

## Costs

- Public repo: GitHub Actions + Pages = **$0** within normal quotas.
- Private repo: Actions minutes apply (~2000 min/month free).

## Related

- Full interactive app: `./run.sh serve` + optional [Cloudflare Tunnel](deploy-w4-tunnel.md) (not included yet).
- Export script: `scripts/export_public_dashboard.py`
