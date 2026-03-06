"""主程序入口"""
import signal
import sys
import time
from spot_orderbook_collector import SpotOrderbookCollector
from futures_orderbook_collector import FuturesOrderbookCollector
from funding_rate_collector import FundingRateCollector
from time_sync import TimeSync
from logger_config import setup_logger
from config import (
    SPOT_SYMBOLS, FUTURES_SYMBOLS,
    SPOT_WS_URL, FUTURES_WS_URL,
    SPOT_DATA_DIR, FUTURES_DATA_DIR
)

# 主程序日志
logger = setup_logger("main")

# 全局采集器引用
spot_collector = None
futures_collector = None
funding_collector = None


def signal_handler(sig, frame):
    """处理SIGINT和SIGTERM信号"""
    _ = sig, frame  # 忽略未使用的参数
    logger.info("收到停止信号，正在停止采集器...")
    if spot_collector is not None:
        spot_collector.stop()
    if futures_collector is not None:
        futures_collector.stop()
    if funding_collector is not None:
        funding_collector.stop()
    logger.info("所有采集器已停止")
    sys.exit(0)


if __name__ == "__main__":
    logger.info("=" * 60)
    logger.info("Binance Orderbook 采集器启动")
    logger.info("=" * 60)

    try:
        # 时间同步
        time_sync = TimeSync()
        logger.info("正在同步服务器时间...")
        if not time_sync.sync_time():
            logger.critical("时间同步失败，程序退出")
            sys.exit(1)

        # 注册信号处理（在创建采集器之前）
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)

        # 创建现货采集器
        spot_collector = SpotOrderbookCollector(
            symbols=SPOT_SYMBOLS,
            ws_url=SPOT_WS_URL,
            data_dir=SPOT_DATA_DIR,
            market_type="spot"
        )

        # 创建合约采集器
        futures_collector = FuturesOrderbookCollector(
            symbols=FUTURES_SYMBOLS,
            ws_url=FUTURES_WS_URL,
            data_dir=FUTURES_DATA_DIR,
            market_type="futures"
        )

        # 创建资金费率采集器
        funding_collector = FundingRateCollector(
            symbols=FUTURES_SYMBOLS,
            data_dir=FUTURES_DATA_DIR
        )

        # 启动采集器
        spot_collector.start()
        futures_collector.start()
        funding_collector.start()

        logger.info("=" * 60)
        logger.info("所有采集器运行中... 按Ctrl+C停止")
        logger.info("提示：所有时间戳均使用Binance服务器时间（UTC），确保数据时间对齐")
        logger.info("=" * 60)

        # 保持主线程运行，使用循环代替signal.pause()以便添加健康检查
        while True:
            time.sleep(1)

    except Exception as e:
        logger.critical(f"程序启动失败: {e}", exc_info=True)
        sys.exit(1)
