# 个股相对强度（RS）与新股分池

> **数据源**：全市场 RS 与新股缩短档均来自 **Finviz Elite export**（`FINVIZ_AUTH_KEY` 必填）。无 token 时管道会失败，无 Yahoo/Stooq 兜底。

## 两套 RS 池（互斥）

| 池 | 条件 | 约数量级 |
|----|------|----------|
| **主 RS** | Elite 五周期 perf 齐全（周/月/季/半年/年） | ~5000+ |
| **新股 RS** | Elite 部分周期 perf（M/Q/H/3Q 档） | 视上市时长 |

同一只股票、同一快照日**只进一个池**，不会同时参与主 RS 与新股 RS 排名。

观察名单合并规则：

- 主 RS Top10% ∩ Top 10 行业 Elite 筛股（`thresholds.top_list_count`）  
- ∪ 新股各档榜单 ∩ Top 10 行业个股  
- **合并为一张最终观察名单**（按 `rs_score` 排序）  
- 若 symbol 重复：**保留主 RS 侧结果**

## 主 RS

- 五周期 perf 来自 Elite export v=141（与行业组排名周期一致）
- 权重：`config.yaml` → `weights`（自动归一化）
- 分位加权 → `rs_score`；Tier A/B/C 阈值默认 0.8 / 0.65
- 实现：`src/stock_rs.py` → `compute_and_store_stock_rs`

## 新股 RS 四档（Elite 缩短 perf）

按 Elite 可用周期归入**最高一档**（互斥）：

| 档位 | Elite perf | 参与排名的周期 |
|------|------------|----------------|
| **M** | 周 + 月 | 周、月 |
| **Q** | + 季 | 周、月、季 |
| **H** | + 半年 | 周、月、季、半年 |
| **3Q** | + 年(YTD) | 周、月、季、半年、三季 |

- 每档内排名规则与主 RS 相同（档内权重归一化）
- 每档取 **Top 10%**（`cross_top_percent`）→ `in_leaderboard = 1`

配置：`stock_rs.new_stock_enabled`（默认 `true`）

## 交叉与观察名单

1. Top 强势行业 → Elite per-industry export（`stock_filters`）→ `stock_picks`  
2. 主 RS 排名前 10% 且 symbol 在行业筛股中 → 候选  
3. 新股各档榜单且 symbol 在行业筛股中 → 候选  
4. 合并去重 → `stock_watchlist` → 决策中心 **Finviz 日 K 图**

## 数据表

| 表 | 说明 |
|----|------|
| `stock_rs_daily` | 主 RS 快照 |
| `stock_rs_new_daily` | 新股 RS（含 `cohort`、`perf_tq`、`in_leaderboard`） |
| `stock_rs_issues` | `elite_no_perf` 等 |
| `stock_rs_meta` | 覆盖率 + 新股各档计数 |
| `stock_watchlist` | 最终观察名单 |

## API

- `GET /api/rs/{date}`：`rows`、`new_stock_leaderboard`、`watchlist`、`rs_meta`

## 未纳入主 RS / 新股缩短档

- `elite_no_perf`：Elite export 缺 perf 字段  
- 主 RS 五周期齐全者走主榜，不走缩短档  

## 行业筛股与观察名单

- **行业 pick**：Elite screener export 后按主 RS 排序入库，无 RS 分数门槛、无二次 swing/SMA 过滤。
- **新股 leaderboard**：每档 M/Q/H/3Q 用**全 Elite 宇宙**按该档 perf 排名，取市场前 `cross_top_percent`（默认 10%），再与**该档新股（partial perf）**求交进榜。
- **观察名单**：主 RS Top10% ∩ 行业 pick ∪ 新股 leaderboard ∩ 行业 pick。

## 配置项

```yaml
stock_rs:
  rs_data_provider: elite   # 仅 elite；无 FINVIZ_AUTH_KEY 则管道失败
  cross_top_percent: 0.1
  min_daily_dollar_volume_usd: 100000000  # 筛股流动性：当日 price×volume
  new_stock_enabled: true
```
