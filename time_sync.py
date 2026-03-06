"""时间同步工具"""
import time
import requests
from logger_config import setup_logger


class TimeSync:
    """Binance服务器时间同步"""

    def __init__(self):
        self.time_offset = 0  # 本地时间与服务器时间的偏差（毫秒）
        self.last_sync = 0
        self.sync_interval = 3600  # 每小时同步一次
        self.logger = setup_logger("time_sync")

    def sync_time(self, max_retries=3):
        """同步服务器时间，失败时重试"""
        for attempt in range(max_retries):
            try:
                local_time_before = int(time.time() * 1000)
                response = requests.get("https://fapi.binance.com/fapi/v1/time", timeout=5)
                local_time_after = int(time.time() * 1000)

                if response.status_code == 200:
                    server_time = response.json()['serverTime']
                    # 使用往返时间的中点作为本地时间
                    local_time = (local_time_before + local_time_after) // 2
                    self.time_offset = server_time - local_time
                    self.last_sync = time.time()

                    self.logger.info(f"时间同步完成，偏差: {self.time_offset}ms")
                    return True
                else:
                    self.logger.warning(f"时间同步失败，HTTP状态码: {response.status_code}")
            except Exception as e:
                self.logger.error(f"时间同步失败 (尝试 {attempt + 1}/{max_retries}): {e}", exc_info=True)
                if attempt < max_retries - 1:
                    time.sleep(2)  # 重试前等待2秒

        self.logger.critical("时间同步失败，已达最大重试次数")
        return False

    def get_server_time(self):
        """获取当前服务器时间（估算）"""
        # 如果超过同步间隔，重新同步
        if time.time() - self.last_sync > self.sync_interval:
            self.sync_time()

        return int(time.time() * 1000) + self.time_offset

    def should_sync(self):
        """是否需要同步"""
        return time.time() - self.last_sync > self.sync_interval
