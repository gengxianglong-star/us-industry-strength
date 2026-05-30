# 美股行业强势筛选

基于 [Finviz Industry Groups](https://finviz.com/groups?g=industry&v=210&o=name) 的多周期相对排名，筛选强势行业，并与个股 RS 交叉生成观察名单。

数据源：
- Finviz Industry / Screener
- Yahoo Adj Close（个股 RS 价格口径）
- Stockbee Market Monitor（市场宽度）

## 跨平台快速开始（macOS / Windows）

### 方式 A：一键脚本（推荐）

- macOS / Linux
  ```bash
  chmod +x run.sh
  ./run.sh
  ```
- Windows（CMD / PowerShell）
  ```bat
  run.bat
  ```

默认会自动创建虚拟环境、安装依赖并启动 Web（`http://127.0.0.1:8080`）。

### Windows 常见问题（快速排障）

- 提示找不到 `py`：重新安装 Python，并勾选 **Add Python to PATH**
- 依赖安装失败：先设置代理后再执行 `run.bat`
  ```bat
  set HTTPS_PROXY=http://127.0.0.1:7890
  run.bat
  ```
- 提示 8080 被占用：按提示执行
  ```bat
  taskkill /PID <PID> /F
  ```
  然后重新 `run.bat`

### 桌面双击启动（只需做一次）

- macOS
  ```bash
  chmod +x scripts/create-desktop-launcher.sh
  ./scripts/create-desktop-launcher.sh
  ```
  执行后，桌面会生成 `US-Industry-Strength.command`，以后双击它即可启动。

- Windows
  ```bat
  scripts\create-desktop-launcher.bat
  ```
  执行后，桌面会生成 `US-Industry-Strength.cmd`，以后双击它即可启动。

如需先抓取当日快照再启动：
- macOS / Linux：`./run.sh daily`（调用 `scripts/precompute_daily.py`：行业快照 + Top行业个股 + RS + 宽度）
- Windows：`run.bat daily`

仅同步市场宽度（不启动 Web）：
- macOS / Linux：`./run.sh breadth`
- Windows：`run.bat breadth`

## 定时同步（cron / launchd）

工作日自动跑「每日预计算（行业 + 个股 + RS + 宽度）」：

```bash
chmod +x scripts/scheduled_daily.sh scripts/install-macos-schedule.sh
./scripts/install-macos-schedule.sh   # macOS：工作日 06:30，日志在 logs/
```

或参考 `scripts/crontab.example` 自行配置 cron。手动执行一次：

```bash
./scripts/scheduled_daily.sh
```

### 方式 B：手动命令

- macOS / Linux
  ```bash
  python3 -m venv .venv
  source .venv/bin/activate
  pip install -r requirements.txt
  python scripts/precompute_daily.py
  python -m uvicorn src.server:app --host 127.0.0.1 --port 8080
  ```

- Windows
  ```bat
  py -3 -m venv .venv
  .venv\Scripts\activate
  pip install -r requirements.txt
  python scripts\precompute_daily.py
  python -m uvicorn src.server:app --host 127.0.0.1 --port 8080
  ```

## 配置说明

配置文件：`config.yaml`（网页配置与文件互通）

- `weights`：1W/1M/3M/6M/1Y 权重（自动归一化）
- `thresholds`：行业评分阈值、趋势参数
- `stock_filters`：Finviz 个股筛选（SMA、成交额、EPS/Sales QoQ>10% 等，见 `fa_epsqoq_o10` / `fa_salesqoq_o10`）
- `scraper.stock_pick_workers`：行业个股抓取并发（建议 2–4，默认 3）
- `thresholds.top_list_count`：强势行业数量（默认 15）
- `scraper.cookie_file`：可选，浏览器导出 Cookie 以绕过 Cloudflare 验证页
- `stock_rs`：个股 RS 抓取与交叉参数

市场宽度页的驾驶舱阈值、5/10 日背景分档、API 与联动逻辑见 **[docs/breadth.md](docs/breadth.md)**（与页面「驾驶舱规则说明」一致，适合长期留存）。

### 只读跨平台看板（GitHub Pages · 零成本）

手机 / 任意浏览器只读查看（无改配置、无手动 RS）：见 **[docs/deploy-readonly-pages.md](docs/deploy-readonly-pages.md)**。

- 地址：`https://<user>.github.io/us-industry-strength/strong`
- 更新：GitHub Actions 工作日自动跑 Daily → 导出 JSON → 发布 Pages
- 本地仍用 `./run.sh serve` 获得完整交互版

个股 RS、新股四档分池与观察名单合并规则见 **[docs/stock_rs.md](docs/stock_rs.md)**。

### 市场宽度与驾驶舱（摘要）

- **页面**：`http://127.0.0.1:8080/breadth` — Stockbee Sheet 同步、宽表、7 格驾驶舱、历史分位、图表。
- **驾驶舱**：季度/半季/月度/5-10 交叉（涨跌对比 → 红绿 BULL/LONG 等）；5 日/10 日 ratio 状态灯 + **背景按锚点分档**（绿锚 1.5、红锚 0.75，两侧各 5 档）；T2108 极值白/红/绿。
- **配置**：页面底部或 `PUT /api/breadth/config`；持久化在 SQLite `breadth_threshold_config`。
- **联动**：点击驾驶舱卡片高亮对应图表曲线（详见 [docs/breadth.md](docs/breadth.md)）。

## GitHub 上传与跨平台维护建议

### 1) 当前仓库状态

如果你看到：
- `git log` 提示 “does not have any commits yet”
- `git remote -v` 为空

说明：仓库已初始化，但还没有首个提交，也未绑定 GitHub 远端。

### 2) 如何查看你的 GitHub 仓库地址

- 打开 GitHub 网页，进入目标仓库首页
- 浏览器地址栏就是仓库地址，例如：
  - `https://github.com/<你的用户名>/<仓库名>`
  - SSH 形式：`git@github.com:<你的用户名>/<仓库名>.git`

### 3) 首次提交并绑定远端（本项目）

```bash
git add .
git commit -m "Initial commit: industry strength screener"
git remote add origin <你的仓库地址>
git push -u origin main
```

如果 `origin` 已存在但地址不对：
```bash
git remote set-url origin <你的仓库地址>
```

## 目录结构

```text
config.yaml
run_daily.py
run.sh
run.bat
docs/
  breadth.md          # 市场宽度与驾驶舱完整说明
scripts/
  precompute_daily.py # 每日预计算：行业+个股+RS+宽度
  sync_breadth.py     # 宽度增量同步
  scheduled_daily.sh  # 定时触发 precompute_daily.py
src/
web/
data/                # SQLite（已 gitignore）
```

## 免责声明

仅供研究学习，不构成投资建议。请遵守数据源网站服务条款并控制抓取频率。
