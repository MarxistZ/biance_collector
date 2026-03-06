# Binance Orderbook实时采集器

实时采集Binance现货和合约市场的orderbook数据，以及合约市场的资金费率等特有数据，并以Parquet格式存储。

## Vultr/生产环境部署

**推荐配置：**
- 安装路径：`/opt/binance_collector`
- 数据存储：`/data`（独立挂载点，建议100GB+）
- 运行用户：root（或创建专用用户）
- 管理方式：systemd服务

**快速部署步骤：**

```bash
# 1. 确保/data挂载点存在且有足够空间
df -h /data

# 2. 克隆代码到/opt
cd /opt
git clone <repo-url> binance_collector
cd binance_collector

# 3. 创建Python虚拟环境（推荐）
python3 -m venv venv
source venv/bin/activate

# 4. 安装依赖
pip3 install -r requirements.txt

# 5. 设置执行权限
chmod +x *.sh

# 6. 配置systemd服务使用venv
sed -i 's|ExecStart=/usr/bin/python3|ExecStart=/opt/binance_collector/venv/bin/python3|' binance-collector.service

# 7. 安装systemd服务
cp binance-collector.service /etc/systemd/system/
systemctl daemon-reload
systemctl enable binance-collector
systemctl start binance-collector

# 8. 验证运行状态
systemctl status binance-collector
journalctl -u binance-collector -f
```

详细部署说明请参考 [DEPLOYMENT.md](DEPLOYMENT.md)。

## 功能特性

- 实时采集现货和合约市场orderbook数据（WebSocket推送，100ms更新频率）
- 采集合约市场资金费率、标记价格、指数价格、未平仓合约量等数据（REST API轮询，10秒更新频率）
- 支持多个交易对同时采集
- 数据以Parquet格式存储，支持高效压缩和查询
- 按日期和小时自动分片存储
- 内存缓存机制：数据在内存中累积，每60秒批量写入硬盘一次

## 支持的交易对

- BTC/USDT
- ETH/USDT
- SOL/USDT
- XRP/USDT
- DOGE/USDT

每个币种同时采集现货和合约市场数据。

## 安装依赖

**推荐：使用Python虚拟环境**

```bash
# 创建虚拟环境
python3 -m venv venv

# 激活虚拟环境
source venv/bin/activate

# 安装依赖
pip install -r requirements.txt
```

**或者：全局安装（不推荐）**

```bash
pip install -r requirements.txt
```

## 运行

**如果使用虚拟环境：**

```bash
# 激活虚拟环境
source venv/bin/activate

# 运行程序
python main.py
```

**如果全局安装：**

```bash
python main.py
```

按Ctrl+C停止采集。

## 数据存储结构

**数据目录配置：** 默认使用 `/data` 作为存储路径（适用于生产环境）。如需修改，请编辑 `config.py` 中的 `DATA_DIR` 变量。

```
/data/
├── spot/
│   ├── BTCUSDT/
│   │   └── 20240307/
│   │       ├── orderbook_00.parquet
│   │       ├── orderbook_01.parquet
│   │       └── ...
│   └── ...
└── futures/
    ├── BTCUSDT/
    │   └── 20240307/
    │       ├── orderbook_00.parquet
    │       ├── funding_rate_00.parquet
    │       └── ...
    └── ...
```

**磁盘空间建议：** 每个交易对每天约产生500MB-1GB数据，建议为 `/data` 分配至少100GB空间。

## 数据字段说明

### 时间戳对齐策略

为确保不同数据源的时间戳对齐，系统采用以下策略：

1. **Orderbook数据**：使用Binance WebSocket推送的事件时间戳（`eventTime`字段）
2. **资金费率数据**：使用Binance REST API返回的服务器时间戳（`time`字段）
3. **时间同步**：系统启动时会同步本地时间与Binance服务器时间，并每小时自动重新同步

所有时间戳均为Binance服务器时间（UTC），单位为毫秒，确保跨数据源的时间一致性。

### Orderbook数据（现货 + 合约）

文件名格式：`orderbook_{HH}.parquet`

| 字段名 | 类型 | 说明 |
|--------|------|------|
| timestamp | int64 | 时间戳（毫秒） |
| symbol | string | 交易对（如BTCUSDT） |
| market_type | string | 市场类型（spot/futures） |
| bids | string | 买单数据，JSON格式，包含价格和数量，最多20档 |
| asks | string | 卖单数据，JSON格式，包含价格和数量，最多20档 |
| last_update_id | int64 | Binance orderbook最后更新ID |

**bids/asks格式示例：**
```json
[["43250.50", "1.234"], ["43250.00", "2.567"], ...]
```
每个元素为 [价格, 数量]

**数据更新频率：** WebSocket实时推送，约100ms更新一次

**保存机制：** 数据在内存中累积，每60秒批量写入硬盘

### 资金费率数据（仅合约）

文件名格式：`funding_rate_{HH}.parquet`

| 字段名 | 类型 | 说明 |
|--------|------|------|
| timestamp | int64 | 采集时间戳（毫秒） |
| symbol | string | 交易对（如BTCUSDT） |
| funding_rate | float64 | 当前资金费率（如0.0001表示0.01%） |
| mark_price | float64 | 标记价格，用于计算未实现盈亏 |
| index_price | float64 | 指数价格，多个现货交易所的加权平均价 |
| next_funding_time | int64 | 下次资金费率结算时间戳（毫秒） |
| open_interest | float64 | 未平仓合约量（张数） |
| volume_24h | float64 | 24小时交易量（张数） |

**数据更新频率：** REST API轮询，每10秒获取一次

**保存机制：** 数据在内存中累积，每60秒批量写入硬盘

## 配置

修改 `config.py` 可以调整：

- 交易对列表
- 数据保存间隔（默认60秒）
- Orderbook深度级别（默认20档）
- 资金费率获取间隔（默认10秒）

## 日志系统

系统使用Python的`logging`模块记录运行日志：

**日志文件位置：** `logs/` 目录

**日志文件：**
- `main.log` - 主程序日志
- `orderbook_spot.log` - 现货orderbook采集日志
- `orderbook_futures.log` - 合约orderbook采集日志
- `funding_rate.log` - 资金费率采集日志
- `time_sync.log` - 时间同步日志

**日志特性：**
- 按天自动轮转（每天午夜创建新日志文件）
- 保留最近30天的日志
- 日志文件命名格式：`{name}.log.{YYYYMMDD}`
- 同时输出到控制台和文件
- 包含时间戳、日志级别、模块名称和详细信息
- 错误日志包含完整的堆栈跟踪信息

**日志级别：**
- INFO：正常运行信息（启动、停止、数据保存等）
- WARNING：警告信息（连接关闭等）
- ERROR：错误信息（包含完整异常堆栈）

**日志格式示例：**
```
2024-03-07 14:30:15 - orderbook_spot - INFO - 已保存 1234 条记录到 data/spot/BTCUSDT/20240307/orderbook_14.parquet
2024-03-07 14:30:20 - funding_rate - ERROR - 获取 ETHUSDT 资金费率失败: Connection timeout
```
