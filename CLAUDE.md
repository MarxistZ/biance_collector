# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Binance orderbook实时数据采集系统，采集现货和合约市场的orderbook数据，以及合约市场的资金费率、标记价格、未平仓合约量等特有数据，并以Parquet格式存储。

**时间戳对齐策略：** 所有数据均使用Binance服务器时间戳，确保跨数据源的时间一致性。Orderbook使用WebSocket事件时间，资金费率使用REST API返回的服务器时间。系统启动时会同步本地时间与服务器时间。

## Architecture

- `main.py`: 程序入口，创建并启动现货、合约orderbook采集器和资金费率采集器
- `orderbook_collector.py`: OrderbookCollector类，处理WebSocket连接、数据接收和Parquet存储
- `funding_rate_collector.py`: FundingRateCollector类，通过REST API获取合约市场资金费率等数据
- `time_sync.py`: TimeSync类，同步本地时间与Binance服务器时间
- `logger_config.py`: 日志配置模块，提供按天轮转的日志记录功能
- `config.py`: 配置文件，包含交易对列表、WebSocket URL、存储路径等

### Data Flow

**Orderbook数据流：**
1. 通过WebSocket连接Binance的depth stream
2. 接收实时orderbook更新（100ms频率）
3. 在内存中缓存数据
4. 每60秒自动保存到Parquet文件
5. 按日期和小时分片存储

**资金费率数据流：**
1. 通过REST API每10秒轮询一次
2. 获取资金费率、标记价格、指数价格、未平仓合约量、24h交易量
3. 在内存中缓存数据
4. 每60秒自动保存到Parquet文件
5. 按日期和小时分片存储

### Storage Structure

```
data/
├── spot/          # 现货市场
│   └── {SYMBOL}/
│       └── {YYYYMMDD}/
│           └── orderbook_{HH}.parquet
└── futures/       # 合约市场
    └── {SYMBOL}/
        └── {YYYYMMDD}/
            ├── orderbook_{HH}.parquet
            └── funding_rate_{HH}.parquet
```

## Commands

### Setup
```bash
pip install -r requirements.txt
```

### Run
```bash
python main.py
```

### Stop
按 Ctrl+C 停止采集器，会自动保存剩余数据

## Key Configuration

- 支持的交易对: BTC, ETH, SOL, XRP, DOGE (USDT交易对)
- Orderbook深度: 20档
- Orderbook更新频率: WebSocket推送，约100ms
- 资金费率获取频率: REST API轮询，10秒
- 保存间隔: 60秒（内存累积数据批量写入硬盘）
- 压缩格式: Snappy

## Data Schema

### Orderbook (spot + futures)
- timestamp, symbol, market_type, bids (JSON), asks (JSON), last_update_id

### Funding Rate (futures only)
- timestamp, symbol, funding_rate, mark_price, index_price, next_funding_time, open_interest, volume_24h

## Dependencies

- websocket-client: WebSocket连接
- pandas: 数据处理
- pyarrow: Parquet文件读写
- requests: REST API请求
- python-binance: Binance API（预留）

## Logging

系统使用Python标准logging模块，日志文件位于`logs/`目录：
- 按天自动轮转（每天午夜）
- 保留30天历史日志
- 同时输出到控制台和文件
- 错误日志包含完整堆栈跟踪

日志文件：main.log, orderbook_spot.log, orderbook_futures.log, funding_rate.log, time_sync.log
