"""配置文件"""

# 交易对配置
SPOT_SYMBOLS = [
    "BTCUSDT",
    "ETHUSDT",
    "SOLUSDT",
    "XRPUSDT",
    "DOGEUSDT"
]

FUTURES_SYMBOLS = [
    "BTCUSDT",
    "ETHUSDT",
    "SOLUSDT",
    "XRPUSDT",
    "DOGEUSDT"
]

# WebSocket配置
SPOT_WS_URL = "wss://stream.binance.com:9443/ws"
FUTURES_WS_URL = "wss://fstream.binance.com/ws"

# 数据存储配置
# 生产环境使用 /data 作为数据存储目录（Vultr VPS专用挂载点）
# 开发环境自动使用本地 ./data 目录
import os
from pathlib import Path

if Path("/data").exists() and os.access("/data", os.W_OK):
    DATA_DIR = "/data"
else:
    DATA_DIR = str(Path(__file__).parent / "data")

SPOT_DATA_DIR = f"{DATA_DIR}/spot"
FUTURES_DATA_DIR = f"{DATA_DIR}/futures"

# Orderbook深度
DEPTH_LEVEL = 20
