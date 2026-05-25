"""日志配置模块

日志文件结构:
  logs/
  ├── collector.log              # 所有模块的合并日志（便于整体排查）
  ├── collector.log.2026-03-09   # 按天轮转的历史日志
  ├── error.log                  # 仅 WARNING 及以上级别（快速定位问题）
  ├── spot.log                   # 现货采集器专用日志
  ├── futures.log                # 合约采集器专用日志
  └── funding.log                # 资金费率采集器专用日志
"""
import logging
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path
import sys

# 日志目录
LOG_DIR = Path("logs")
LOG_DIR.mkdir(parents=True, exist_ok=True)

# 模块名 -> 简短日志文件名映射
_MODULE_FILE_MAP = {
    "main": "collector",
    "orderbook_spot": "spot",
    "orderbook_futures": "futures",
    "funding_rate": "funding",
}

# ── 格式定义 ──────────────────────────────────────────────
# 文件格式：含毫秒精度和模块标识
_FILE_FMT = logging.Formatter(
    fmt="%(asctime)s.%(msecs)03d | %(levelname)-7s | %(name)-18s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

# 控制台格式：更紧凑
_CONSOLE_FMT = logging.Formatter(
    fmt="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
    datefmt="%H:%M:%S",
)

# ── 共享 Handler（只创建一次）─────────────────────────────
_shared_handlers_initialized = False
_combined_handler = None
_error_handler = None


def _init_shared_handlers():
    """初始化全局共享的 handler（合并日志 + 错误日志）"""
    global _shared_handlers_initialized, _combined_handler, _error_handler
    if _shared_handlers_initialized:
        return
    _shared_handlers_initialized = True

    # 合并日志 - 所有模块的 INFO 级别日志汇总到一个文件
    _combined_handler = TimedRotatingFileHandler(
        filename=LOG_DIR / "collector.log",
        when="midnight",
        interval=1,
        backupCount=30,
        encoding="utf-8",
    )
    _combined_handler.setLevel(logging.INFO)
    _combined_handler.setFormatter(_FILE_FMT)
    _combined_handler.suffix = "%Y-%m-%d"

    # 错误日志 - 仅 WARNING 及以上，方便快速排查
    _error_handler = TimedRotatingFileHandler(
        filename=LOG_DIR / "error.log",
        when="midnight",
        interval=1,
        backupCount=60,
        encoding="utf-8",
    )
    _error_handler.setLevel(logging.WARNING)
    _error_handler.setFormatter(_FILE_FMT)
    _error_handler.suffix = "%Y-%m-%d"


def setup_logger(name, log_dir="logs", level=logging.INFO):
    """
    配置日志记录器

    每个模块的日志会同时写入:
      1. 模块专用日志文件 (如 spot.log)
      2. 合并日志文件 (collector.log)
      3. 错误日志文件 (error.log, 仅 WARNING+)
      4. 控制台 (stdout)

    Args:
        name: 日志记录器名称 (main / orderbook_spot / orderbook_futures / funding_rate)
        log_dir: 日志文件目录（保留兼容，实际使用 LOG_DIR）
        level: 日志级别

    Returns:
        logger: 配置好的日志记录器
    """
    logger = logging.getLogger(name)
    logger.setLevel(level)
    logger.propagate = False

    # 避免重复添加 handler
    if logger.handlers:
        return logger

    # 初始化共享 handler
    _init_shared_handlers()

    # 模块专用日志文件
    log_filename = _MODULE_FILE_MAP.get(name, name)
    module_handler = TimedRotatingFileHandler(
        filename=LOG_DIR / f"{log_filename}.log",
        when="midnight",
        interval=1,
        backupCount=30,
        encoding="utf-8",
    )
    module_handler.setLevel(level)
    module_handler.setFormatter(_FILE_FMT)
    module_handler.suffix = "%Y-%m-%d"

    # 控制台 handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(level)
    console_handler.setFormatter(_CONSOLE_FMT)

    # 添加所有 handler
    logger.addHandler(module_handler)
    logger.addHandler(_combined_handler)
    logger.addHandler(_error_handler)
    logger.addHandler(console_handler)

    return logger
