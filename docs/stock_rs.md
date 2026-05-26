# 个股相对强度（RS）与新股分池

## 两套 RS 池（互斥）

| 池 | 条件 | 约数量级 |
|----|------|----------|
| **主 RS** | 有效日线 ≥ `min_price_rows`（默认 260） | ~5773 |
| **新股 RS** | 22 ≤ 日线 < 260，且能算对应档位收益 | ~1000+ 中可分子集 |

同一只股票、同一快照日**只进一个池**，不会同时参与主 RS 与新股 RS 排名。

观察名单合并规则：

- 主 RS Top10% ∩ Top15 行业 Finviz 个股（`thresholds.top_list_count`）  
- ∪ 新股 RS 各档 Top10% ∩ Top15 行业个股  
- **合并为一张最终观察名单**（按 `rs_score` 排序），**不标注来源**  
- 若极端情况下 symbol 重复：**保留主 RS 侧结果**（正常不应发生）

## 主 RS

- 五周期：1W / 1M / 3M / 6M / 1Y（交易日偏移 5 / 21 / 63 / 126 / 252）
- 权重：`config.yaml` → `weights`（自动归一化）
- 分位加权 → `rs_score`；Tier A/B/C 阈值默认 0.8 / 0.65
- 实现：`src/stock_rs.py` → `compute_and_store_stock_rs`

## 新股 RS 四档

按 **K 线根数** 归入**最高一档**（互斥）：

| 档位 | Bar 数 | 参与排名的周期 |
|------|--------|----------------|
| **M** | 22 ≤ N < 63 | 周、月 |
| **Q** | 63 ≤ N < 126 | 周、月、季 |
| **H** | 126 ≤ N < 189 | 周、月、季、半年 |
| **3Q** | 189 ≤ N < 260 | 周、月、季、半年、**三季（189 交易日）** |

- 每档内排名规则与主 RS 相同：档内各周期分位 + 权重（仅对**该档可用周期**归一化；三季周期沿用 `weights.year`）
- 每档取 **Top 10%**（`cross_top_percent`，默认 0.1）→ `stock_rs_new_daily.in_leaderboard = 1`
- N < 22：不参与新股 RS

配置：`config.yaml` → `stock_rs.new_stock_enabled`（默认 `true`）

## 交叉与观察名单

1. Top15 强势行业 → Finviz 筛股（含 EPS/Sales QoQ>30% 等）→ `stock_picks`  
2. 主 RS 排名前 10% 且 symbol 在行业筛股中 → 候选  
3. 新股各档榜单（已是档内 Top10%）且 symbol 在行业筛股中 → 候选  
4. 合并去重 → `stock_watchlist` → 决策中心 **Finviz 日 K**

## 数据表

| 表 | 说明 |
|----|------|
| `stock_rs_daily` | 主 RS 快照 |
| `stock_rs_new_daily` | 新股 RS（含 `cohort`、`perf_tq`、`in_leaderboard`） |
| `stock_rs_issues` | `no_bars` / `insufficient_history` / `perf_invalid` |
| `stock_rs_meta` | 覆盖率 + 新股各档计数 |
| `stock_watchlist` | 最终观察名单 |

## API

- `GET /api/rs/{date}`：`rows`、`new_stock_leaderboard`、`watchlist`、`rs_meta`

## 未纳入新股 RS

- `no_bars`：Yahoo/Stooq 无数据  
- 主 RS 已成功者（≥260 日）  
- 刷新 RS 时仅对**当次拉取到 K 线**的 `insufficient_history` 计算新股榜；增量模式下若未重拉则可能没有 bars，需再点「刷新个股RS」

## 配置项

```yaml
stock_rs:
  min_price_rows: 260
  cross_top_percent: 0.1
  new_stock_enabled: true
```
