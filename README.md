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

如需先抓取当日快照再启动：
- macOS / Linux：`./run.sh daily`
- Windows：`run.bat daily`

### 方式 B：手动命令

- macOS / Linux
  ```bash
  python3 -m venv .venv
  source .venv/bin/activate
  pip install -r requirements.txt
  python run_daily.py
  python -m uvicorn src.server:app --host 127.0.0.1 --port 8080
  ```

- Windows
  ```bat
  py -3 -m venv .venv
  .venv\Scripts\activate
  pip install -r requirements.txt
  python run_daily.py
  python -m uvicorn src.server:app --host 127.0.0.1 --port 8080
  ```

## 配置说明

配置文件：`config.yaml`（网页配置与文件互通）

- `weights`：1W/1M/3M/6M/1Y 权重（自动归一化）
- `thresholds`：行业评分阈值、趋势参数
- `stock_filters`：Finviz 个股筛选条件（默认含 $100M 成交额过滤）
- `stock_rs`：个股 RS 抓取与交叉参数

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
src/
web/
data/                # SQLite（已 gitignore）
```

## 免责声明

仅供研究学习，不构成投资建议。请遵守数据源网站服务条款并控制抓取频率。
