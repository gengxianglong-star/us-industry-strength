# 市场宽度与驾驶舱

本文档记录 **Breadth 页面**（`/breadth`）的数据来源、存储、驾驶舱逻辑、背景色阶与图表联动，便于换机、换账号或长期维护时查阅。页面内「驾驶舱规则说明」由 API 根据当前阈值动态生成，与此文档一致。

## 数据源与同步

| 项目 | 说明 |
|------|------|
| 来源 | Stockbee [Market Monitor](https://stockbee.blogspot.com/2022/12/market-monitor-scans.html) 公开 Google Sheet |
| Sheet ID | `1O6OhS7ciA8zwfycBfGPbP2fWJnR0pn2UUvFZVDP9jpE`（见 `src/breadth_data.py`） |
| 主表 gid | `1082103394`（Market Monitor，与 Stockbee 公开链接一致） |
| 增量逻辑 | 新日期 + **最近 120 天**整段重拉（Sheet 会修订已发布行，如 Down 4% 118→119） |
| 全量 | `POST /api/breadth/sync?full=true` 或 `python scripts/sync_breadth.py --full` |
| 校验 | `python scripts/validate_breadth.py`（可选 `--sync`） |

**命令行同步（不启动 Web）：**

```bash
./run.sh breadth
# 或
python scripts/sync_breadth.py
```

**定时任务：** 见根目录 `README.md` →「定时同步」；日志在 `logs/scheduled-YYYYMMDD.log`。

## SQLite 表（`data/*.db`）

| 表名 | 用途 |
|------|------|
| `breadth_sheet_meta` | 每个 gid 的元数据、首尾日期 |
| `breadth_raw_daily` | 按 gid 的原始行（含 `raw_values` JSON） |
| `breadth_daily` | 按交易日合并后的宽表（`c1`…`c15` 数值列） |
| `breadth_threshold_config` | 驾驶舱阈值与背景分档覆盖项（key/value） |

合并字段与表头对应关系（API 中 `c1`…`c15`）：

| 列 | 含义 |
|----|------|
| c1 / c2 | 当日 Up 4% / Down 4% 家数 |
| c3 / c4 | 5 日 / 10 日 ratio |
| c5 / c6 | 季度 Up25% / Down25% |
| c7 / c8 | 月度 Up25% / Down25% |
| c9 / c10 | 月度 Up50% / Down50% |
| c11 / c12 | 34 日 Up13% / Down13% |
| c14 | T2108 |
| c15 | S&P |

## HTTP API

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/breadth` | 市场宽度 HTML 页 |
| GET | `/api/breadth?limit=&refresh=` | 表格、驾驶舱 `status`、分位卡、阈值、`ratio_bg`、`cockpit_help` |
| POST | `/api/breadth/sync?full=&async_mode=` | 触发同步 |
| GET | `/api/breadth/sync-progress` | 异步同步进度 |
| GET/PUT | `/api/breadth/config` | 读取/保存 `breadth_threshold_config` |

实现入口：`src/breadth_data.py`（业务）、`src/server.py`（路由）。

## 驾驶舱：7 个模块

最新一行宽表数据驱动，逻辑在 `load_breadth_data()` → `status` 字段。

| 模块 | 判定（灯色 + 文案） | 背景板 |
|------|---------------------|--------|
| **季度趋势** | Up25%Q > Down25%Q → 绿 `BULL`，否则红 `BEAR` | 与四模块「满强度」灯色一致（绿 `#1b5e3a` / 红 `#5e343c`） |
| **半季趋势** | Up13%/34D > Down13%/34D → 绿 `BULL`，否则红 `BEAR` | 同上 |
| **月度趋势** | Up25%M > Down25%M → 绿 `BULLISH`，否则红 `BEARISH` | 同上 |
| **5-10 交叉** | 5D ratio ≥ 10D ratio → 绿 `LONG`，否则红 `SHORT` | 同上 |
| **10 日趋势** | 见下文「5/10 日状态灯」 | 见下文「5/10 日背景分档」 |
| **5 日趋势** | 同上（独立阈值键 `trend5_*`） | 同上 |
| **极值提醒** | T2108 ≤ red_max → 红 `OVERSOLD`；≥ green_min → 绿 `OVERBOUGHT`；否则白 `NORMAL` | 白灯时背景 `#1a2433` |

### 5/10 日状态灯（`_ratio_trend_state`）

对应当日 **c4（10D）** 或 **c3（5D）** 比值，阈值可分别配置：

| 条件 | 状态 | 灯色 | 强度 |
|------|------|------|------|
| ratio ≥ `trend*_overbought_min` | OVERBOUGHT | 绿 | 随超出幅度 0–1 |
| ratio ≤ `trend*_oversold_max` | OVERSOLD | 红 | 随低于幅度 0–1 |
| 中间且 ratio ≥ 1 | NORMAL | 绿 | 随 (ratio−1) 升高 |
| 中间且 ratio < 1 | NORMAL | 红 | 随 (1−ratio) 升高 |

默认：Overbought ≥ **2.0**，Oversold ≤ **0.5**（10D/5D 相同默认值）。

## 5/10 日趋势：背景色阶

仅 **5 日 / 10 日** 两张卡在灯为绿/红时使用分档背景；四模块趋势卡始终用基准绿/红底色。

配置项保存在 `breadth_threshold_config`（页面底部「阈值与背景分档配置」），默认值见 `DEFAULT_THRESHOLDS`。

### 绿灯（翠绿阶梯）

| 参数 | 默认 | 含义 |
|------|------|------|
| `ratio_green_anchor` | 1.5 | 与四模块绿灯背景一致 |
| `ratio_green_low_min` | 1.0 | 区间下限 |
| `ratio_green_high_max` | 2.0 | 区间上限 |
| `ratio_green_tier_count` | 5 | 锚点以下、以上各 5 档 |

- **ratio = 锚点** → 基准绿 `#1b5e3a`
- **锚点以下**（1.0 → 1.5）→ 每档变浅（步长 = (锚点−下限)/档数）
- **锚点以上**（1.5 → 2.0）→ 每档加深
- 超出区间 → 顶在最浅/最深档

### 红灯（玫红阶梯）

| 参数 | 默认 | 含义 |
|------|------|------|
| `ratio_red_anchor` | 0.75 | 与四模块红灯背景一致 |
| `ratio_red_low_min` | 0.5 | 区间下限 |
| `ratio_red_high_max` | 1.0 | 区间上限 |
| `ratio_red_tier_count` | 5 | 锚点以下、以上各 5 档 |

- **ratio = 锚点** → 基准红 `#5e343c`
- **锚点以下**（0.5 → 0.75）→ 每档**加深**
- **锚点以上**（0.75 → 1.0）→ 每档**变浅**

前端实现：`web/static/breadth.js`（`ratioGreenTrendBackground` / `ratioRedTrendBackground`）。色板为不透明 hex，避免 rgba 叠底造成深浅错觉。

## 配置项一览

**状态灯：**

- `trend10_overbought_min` / `trend10_oversold_max`
- `trend5_overbought_min` / `trend5_oversold_max`
- `t2108_red_max` / `t2108_green_min`（默认 20 / 60）

**背景分档：** 见上表 `ratio_green_*`、`ratio_red_*`。

保存时服务端 `validate_breadth_thresholds()` 校验：锚点区间、档数 2–10、Oversold < Overbought、T2108 red < green。

## 图表与驾驶舱联动

点击驾驶舱卡片 → 下方对应 Chart.js 图表高亮序列，其余变淡；再点取消。映射（`COCKPIT_CHART_LINK`）：

| 驾驶舱模块 | 图表 canvas | 高亮序列 |
|------------|-------------|----------|
| 季度趋势 | `quarter25Chart` | Up/Down 25% Quarter |
| 半季趋势 | `spxBreadthChart` | Up/Down 13%/34D |
| 月度趋势 | `month25Chart` | Up/Down 25% Month |
| 5-10 交叉 | `ratioChart` | 5 Day + 10 Day Ratio |
| 10 日趋势 | `ratioChart` | 10 Day Ratio |
| 5 日趋势 | `ratioChart` | 5 Day Ratio |
| 极值提醒 | `ratioChart` | T2108 |

## 前端文件

| 文件 | 作用 |
|------|------|
| `web/breadth.html` | 页面结构 |
| `web/static/breadth.js` | 驾驶舱、图表、联动、配置表单 |
| `web/static/breadth.css` | 驾驶舱网格、色阶、联动样式 |

静态资源带 `?v=` 版本号，改版后请硬刷新或 bump 版本避免缓存。

## 历史分位卡

`percentile_cards`：对 Up4%、Down4%、10D ratio、Up/Down 25%Q、T2108 等序列计算**当前值在历史中的百分位**（`_pct_rank`），用于 Time Series 区域展示。

## 与强势行业页的关系

- **Strong Industry**（`/strong`）：Finviz 行业排名、RS、观察名单（`config.yaml` + `run_daily.py`）。
- **Breadth**（`/breadth`）：市场宽度环境，独立 SQLite 表与阈值，不写入行业快照。
- 二者通过顶栏导航切换；尚未在强势行业页嵌入驾驶舱摘要（可作为后续增强）。

## 维护备忘

1. 改驾驶舱逻辑：优先改 `src/breadth_data.py`，再同步 `build_cockpit_help()` 与本文档。
2. 改背景色阶：改 `breadth.js` 色数组 + `ratio_*` 默认值；用户覆盖存在 DB，不会自动迁移。
3. API 无 `cockpit_help`：多为后端未重启；前端有 `buildCockpitHelpClient` 兜底。
4. 缓存：`load_breadth_data` 内存缓存 TTL 300s；`refresh=true` 会先增量同步再重建 payload。
