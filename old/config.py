"""配置文件"""
import os
from pathlib import Path

# 交易对配置
DEFAULT_SYMBOLS = [
    "BTCUSDT",
    "ETHUSDT",
    "BNBUSDT",
    "SOLUSDT",
    "XRPUSDT",
    "DOGEUSDT",
    "AVAXUSDT",
    "LINKUSDT"
]
SPOT_SYMBOLS = DEFAULT_SYMBOLS.copy()
FUTURES_SYMBOLS = DEFAULT_SYMBOLS.copy()

# WebSocket配置
SPOT_WS_URL = "wss://stream.binance.com:9443/ws"
FUTURES_WS_URL = "wss://fstream.binance.com/ws"

# 数据存储配置
if Path("/data").exists() and os.access("/data", os.W_OK):
    DATA_DIR = Path("/data")
else:
    DATA_DIR = Path(__file__).parent / "data"

SPOT_DATA_DIR = DATA_DIR / "spot"
FUTURES_DATA_DIR = DATA_DIR / "futures"

# Orderbook深度
DEPTH_LEVEL = 20
