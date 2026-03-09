# 币安数据采集器最终数据结构 (Raw Data Schema)

本文档根据项目代码实现 (`config.py`, `base_orderbook_collector.py`, `spot_orderbook_collector.py`, `futures_orderbook_collector.py`, `funding_rate_collector.py`) 梳理的数据接收并保存下来的最终结构。

## 1. 目录结构方式

数据最终存储根目录取决于系统环境：如果服务器存在 `/data` 路径且可写，则存储在 `/data` 下；否则默认存储在项目目录内的 `data/` 文件夹下。

整体目录结构使用**按市场 -> 按交易对 -> 按天 (UTC 日期)**的方式进行分层级划分：

```text
data/
├── spot/                                 # 现货市场数据目录
│   └── {SYMBOL}/                         # 交易对名称 (例如: BTCUSDT)
│       └── {YYYYMMDD}/                   # UTC日期目录 (例如: 20260309)
│           └── orderbook_{HH}.parquet    # 现货订单簿文件
└── futures/                              # 合约市场数据目录
    └── {SYMBOL}/                         # 交易对名称 (例如: BTCUSDT)
        └── {YYYYMMDD}/                   # UTC日期目录 (例如: 20260309)
            ├── orderbook_{HH}.parquet    # 合约订单簿文件
            └── funding_rate_{HH}.parquet # 合约资金费率及统计数据文件
```

## 2. 文件名命名方式

写入的文件均采用高压缩率的 **Parquet** 格式，使用 `snappy` 进行数据压缩处理，并且根据 UTC 时间 **按小时** 生成独立的文件，达到自动切割轮转的目的。

*   **订单簿文件 (现货/合约均适用):** `orderbook_{HH}.parquet` (例如 `orderbook_13.parquet` 表示 13:00 - 13:59 期间的数据)。如果在同一小时内重启采集器，新数据会自动追加 (concat) 到同名文件中。
*   **资金费率文件 (仅合约专属):** `funding_rate_{HH}.parquet` (例如 `funding_rate_13.parquet`)。

---

## 3. 文件内字段 Schema

字段结构通过 `PyArrow` 构建，严格限制了存储类型，共包含以下 3 种不同的数据 Schema 表结构：

### 3.1 现货订单簿表 (Spot Orderbook - 共 85 列)

记录由 WebSocket 接收的现货深度快照 (`depth snapshot`) 数据。

| 字段名称 | 类型 (PyArrow) | 描述 |
| :--- | :--- | :--- |
| `timestamp` | `int64` | websocket事件时间戳 (`E` 字段) |
| `symbol` | `string` | 对应的交易对，如 `BTCUSDT` |
| `market_type` | `string` | 固定值 `"spot"` |
| `first_update_id`| `int64` | 首个更新 ID (在现货处理中与 last_update_id 相同) |
| `bid1_price` ~ `bid20_price`| `float64` | 买单（Bids）第 1 档到第 20 档的**价格** |
| `bid1_qty` ~ `bid20_qty`| `float64` | 买单（Bids）第 1 档到第 20 档的**挂单量** |
| `ask1_price` ~ `ask20_price`| `float64` | 卖单（Asks）第 1 档到第 20 档的**价格** |
| `ask1_qty` ~ `ask20_qty`| `float64` | 卖单（Asks）第 1 档到第 20 档的**挂单量** |
| `last_update_id` | `int64` | 最后的更新 ID (`lastUpdateId`) |

### 3.2 合约订单簿表 (Futures Orderbook - 共 87 列)

记录由 WebSocket 接收的合约深度更新 (`depthUpdate`) 数据，相比现货多了 2 列时间与版本比对相关的元数据。

| 字段名称 | 类型 (PyArrow) | 描述 |
| :--- | :--- | :--- |
| `timestamp` | `int64` | 事件时间戳 (`E`) |
| `symbol` | `string` | 对应的交易对，如 `BTCUSDT` |
| `market_type` | `string` | 固定值 `"futures"` |
| `transaction_time`| `int64` | 撮合引擎时间 (`T`) |
| `first_update_id`| `int64` | 这批变动的首个更新 ID (`U`) |
| `prev_update_id` | `int64` | 前一个推送记录的更新 ID 校验值 (`pu`) |
| `bid1_price` ~ `bid20_price`| `float64` | 买单（Bids）第 1 档到第 20 档的**价格** |
| `bid1_qty` ~ `bid20_qty`| `float64` | 买单（Bids）第 1 档到第 20 档的**挂单量** |
| `ask1_price` ~ `ask20_price`| `float64` | 卖单（Asks）第 1 档到第 20 档的**价格** |
| `ask1_qty` ~ `ask20_qty`| `float64` | 卖单（Asks）第 1 档到第 20 档的**挂单量** |
| `last_update_id` | `int64` | 这批变动最终的更新 ID (`u`) |

### 3.3 合约资金费率综合表 (Futures Funding Rate 及市场盘口 - 共 8 列)

每 15 秒通过 REST API 获取一次的快照统计数据（从 `/fapi/v1/premiumIndex`、`ticker/24hr` 和 `openInterest` 接口整合提取）：

| 字段名称 | 类型 (PyArrow) | 描述 |
| :--- | :--- | :--- |
| `timestamp` | `int64` | 服务器当前精准时间戳 |
| `symbol` | `string` | 对应的交易对，如 `BTCUSDT` |
| `funding_rate` | `float64` | 当前计算出的预测资金费率 (`lastFundingRate`) |
| `mark_price` | `float64` | 标记价格 (`markPrice`) |
| `index_price` | `float64` | 现货指数价格 (`indexPrice`) |
| `next_funding_time`| `int64` | 下次资金费率结算/扣费时间 |
| `open_interest` | `float64` | 市场未平仓合约数量 (`openInterest`) |
| `volume_24h` | `float64` | 近 24 小时内的滚动成交量 (`volume`) |
