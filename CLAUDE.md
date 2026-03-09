# CLAUDE.md

## 项目概述

Binance orderbook实时数据采集系统，采集现货和合约市场的orderbook数据及资金费率，以Parquet格式存储。所有数据使用Binance服务器时间戳，并同时记录本机接收时间戳。

## 架构

- `main.py`: 程序入口
- `base_orderbook_collector.py`: Orderbook采集器基类（WebSocket管理、重连、保存）
- `spot_orderbook_collector.py`: 现货市场采集器
- `futures_orderbook_collector.py`: 合约市场采集器
- `funding_rate_collector.py`: 资金费率采集器（REST API）
- `config.py`: 配置文件
- `logger_config.py`: 日志配置

## 数据流

**Orderbook**: WebSocket → 内存缓存 → 每10秒保存到Parquet（按日期/小时分片）
**资金费率**: REST API每15秒轮询 → 内存缓存 → 每10秒保存到Parquet

## 存储结构

```
data/
├── spot/{SYMBOL}/spot_{SYMBOL}_{YYYYMMDDHH}.parquet
└── futures/{SYMBOL}/
    ├── future_{SYMBOL}_{YYYYMMDDHH}.parquet
    └── funding_{SYMBOL}_{YYYYMMDDHH}.parquet
```

## 部署

```bash
sudo ./deploy.sh install  # 安装依赖
./deploy.sh start          # 启动
./deploy.sh status         # 状态
```

## 配置

- 交易对: BTC, ETH, BNB, SOL, XRP, DOGE, AVAX, LINK (USDT)
- Orderbook深度: 20档
- 更新频率: WebSocket 100ms, 资金费率 15秒
- 保存间隔: 10秒
- 压缩: Snappy

## 数据Schema

**Orderbook**: timestamp, local_timestamp, symbol, market_type, bid1-20_price/qty, ask1-20_price/qty, last_update_id
**资金费率**: timestamp, local_timestamp, symbol, funding_rate, mark_price, index_price, next_funding_time, open_interest, volume_24h

## 日志

日志位于`logs/`目录，按天轮转，保留30天。
