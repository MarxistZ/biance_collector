"""日志配置模块"""
import logging
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path
import sys


def setup_logger(name, log_dir="logs", level=logging.INFO):
    """
    配置日志记录器

    Args:
        name: 日志记录器名称
        log_dir: 日志文件目录
        level: 日志级别

    Returns:
        logger: 配置好的日志记录器
    """
    # 创建日志目录
    log_path = Path(log_dir)
    log_path.mkdir(parents=True, exist_ok=True)

    # 创建logger
    logger = logging.getLogger(name)
    logger.setLevel(level)
    logger.propagate = False

    # 避免重复添加handler
    if logger.handlers:
        return logger

    # 日志格式
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )

    # 文件handler - 按天轮转
    file_handler = TimedRotatingFileHandler(
        filename=log_path / f"{name}.log",
        when='midnight',
        interval=1,
        backupCount=30,  # 保留30天
        encoding='utf-8'
    )
    file_handler.setLevel(level)
    file_handler.setFormatter(formatter)
    file_handler.suffix = "%Y%m%d"  # 日志文件后缀格式

    # 控制台handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(level)
    console_handler.setFormatter(formatter)

    # 添加handlers
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)

    return logger
