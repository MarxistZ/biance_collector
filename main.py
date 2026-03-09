"""主程序入口"""
import signal
import sys
import time
from spot_orderbook_collector import SpotOrderbookCollector
from futures_orderbook_collector import FuturesOrderbookCollector
from funding_rate_collector import FundingRateCollector
from logger_config import setup_logger
from config import (
    SPOT_SYMBOLS, FUTURES_SYMBOLS,
    SPOT_WS_URL, FUTURES_WS_URL,
    SPOT_DATA_DIR, FUTURES_DATA_DIR
)

# 主程序日志
logger = setup_logger("main")

# 全局采集器引用（用于信号处理）
collectors = []


def stop_all_collectors():
    """按注册顺序停止所有采集器"""
    for collector in collectors:
        try:
            collector.stop()
        except Exception as e:
            logger.error(f"停止采集器失败: {e}", exc_info=True)


def signal_handler(sig, frame):
    """处理SIGINT和SIGTERM信号"""
    _ = sig, frame  # 忽略未使用的参数
    logger.info("收到停止信号，正在停止采集器...")
    stop_all_collectors()
    logger.info("所有采集器已停止")
    sys.exit(0)


def main():
    logger.info("=" * 60)
    logger.info("Binance Orderbook 采集器启动")
    logger.info("=" * 60)

    try:
        # 注册信号处理（在创建采集器之前）
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)

        spot_collector = SpotOrderbookCollector(
            symbols=SPOT_SYMBOLS,
            ws_url=SPOT_WS_URL,
            data_dir=SPOT_DATA_DIR,
            market_type="spot"
        )

        futures_collector = FuturesOrderbookCollector(
            symbols=FUTURES_SYMBOLS,
            ws_url=FUTURES_WS_URL,
            data_dir=FUTURES_DATA_DIR,
            market_type="futures"
        )

        funding_collector = FundingRateCollector(
            symbols=FUTURES_SYMBOLS,
            data_dir=FUTURES_DATA_DIR
        )

        collectors.clear()
        collectors.extend([spot_collector, futures_collector, funding_collector])

        for collector in collectors:
            collector.start()

        logger.info("=" * 60)
        logger.info("所有采集器运行中... 按Ctrl+C停止")
        logger.info("提示：所有时间戳均使用Binance服务器时间（UTC），确保数据时间对齐")
        logger.info("=" * 60)

        while True:
            time.sleep(1)

    except Exception as e:
        logger.critical(f"程序启动失败: {e}", exc_info=True)
        stop_all_collectors()
        sys.exit(1)


if __name__ == "__main__":
    main()
