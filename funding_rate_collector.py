"""合约市场资金费率采集器"""
import time
import threading
import shutil
from datetime import datetime, timezone
from pathlib import Path
import requests
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
from logger_config import setup_logger


class FundingRateCollector:
    def __init__(self, symbols, data_dir):
        self.symbols = symbols
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)

        # 设置日志
        self.logger = setup_logger("funding_rate")

        # 改用字典结构，便于按symbol清理
        self.funding_data = {symbol: [] for symbol in symbols}
        self.running = False
        self.data_lock = threading.Lock()

        # Parquet schema
        self.schema = pa.schema([
            ('timestamp', pa.int64()),
            ('symbol', pa.string()),
            ('funding_rate', pa.float64()),
            ('mark_price', pa.float64()),
            ('index_price', pa.float64()),
            ('next_funding_time', pa.int64()),
            ('open_interest', pa.float64()),
            ('volume_24h', pa.float64())
        ])

        self.api_base = "https://fapi.binance.com"
        self.fetch_interval = 15  # 每15秒获取一次（降低API调用频率）
        self.save_interval = 10  # 每10秒保存一次（1GB内存优化）

        self.fetch_thread = None
        self.auto_save_thread = None
        self.session = requests.Session()

        # 内存保护阈值
        self.max_records_per_symbol = 600  # 严格内存限制（1GB VPS）

    @staticmethod
    def _to_float(value, default=0.0):
        try:
            return float(value)
        except (TypeError, ValueError):
            return default

    @staticmethod
    def _to_int(value, default=0):
        try:
            return int(value)
        except (TypeError, ValueError):
            return default

    def _request_json(self, endpoint, symbol, *, required=False):
        """请求单个REST接口，处理常见限流/封禁状态码"""
        url = f"{self.api_base}{endpoint}?symbol={symbol}"
        response = self.session.get(url, timeout=5)
        status_code = response.status_code

        if status_code == 200:
            return response.json()
        if status_code == 429:
            self.logger.warning(f"API速率限制 (429) [{symbol}]，等待60秒")
            time.sleep(60)
            return None
        if status_code == 418:
            self.logger.critical(f"IP被封禁 (418) [{symbol}]，等待10分钟")
            time.sleep(600)
            return None

        message = f"API请求失败 [{symbol}] {endpoint}: HTTP {status_code}"
        if required:
            self.logger.error(message)
        else:
            self.logger.warning(message)
        return None

    def _pop_records(self, symbol):
        with self.data_lock:
            records = self.funding_data[symbol]
            if not records:
                return []
            self.funding_data[symbol] = []
            return records

    def _requeue_records(self, symbol, records):
        if not records:
            return
        with self.data_lock:
            self.funding_data[symbol] = records + self.funding_data[symbol]

    def fetch_funding_rate(self, symbol):
        """获取单个交易对的资金费率和相关数据"""
        try:
            premium_data = self._request_json("/fapi/v1/premiumIndex", symbol, required=True)
            if not premium_data:
                return None

            server_time = premium_data.get("time")
            if server_time is None:
                self.logger.warning(f"资金费率返回缺少time字段 [{symbol}]")
                return None

            ticker_data = self._request_json("/fapi/v1/ticker/24hr", symbol) or {}
            oi_data = self._request_json("/fapi/v1/openInterest", symbol) or {}

            record = {
                "timestamp": self._to_int(server_time),
                "symbol": symbol,
                "funding_rate": self._to_float(premium_data.get("lastFundingRate")),
                "mark_price": self._to_float(premium_data.get("markPrice")),
                "index_price": self._to_float(premium_data.get("indexPrice")),
                "next_funding_time": self._to_int(premium_data.get("nextFundingTime")),
                "open_interest": self._to_float(oi_data.get("openInterest")),
                "volume_24h": self._to_float(ticker_data.get("volume")),
            }

            return record

        except requests.exceptions.Timeout:
            self.logger.warning(f"获取 {symbol} 资金费率超时")
            return None
        except requests.exceptions.RequestException as e:
            self.logger.error(f"获取 {symbol} 资金费率网络错误: {e}")
            return None
        except Exception as e:
            self.logger.error(f"获取 {symbol} 资金费率失败: {e}", exc_info=True)
            return None

    def fetch_loop(self):
        """定时获取资金费率"""
        while self.running:
            cycle_start = time.time()
            for symbol in self.symbols:
                if not self.running:
                    break

                record = self.fetch_funding_rate(symbol)
                if record:
                    with self.data_lock:
                        self.funding_data[symbol].append(record)
                        buffer_size = len(self.funding_data[symbol])

                    if buffer_size == self.max_records_per_symbol + 1:
                        self.logger.warning(f"{symbol} 资金费率缓存超过 {self.max_records_per_symbol} 条")

                time.sleep(0.1)  # 避免请求过快

            elapsed = time.time() - cycle_start
            sleep_seconds = max(0.0, self.fetch_interval - elapsed)
            if sleep_seconds > 0:
                time.sleep(sleep_seconds)

    def _check_disk_space(self):
        """检查磁盘可用空间"""
        try:
            stat = shutil.disk_usage(self.data_dir)
            free_gb = stat.free / (1024 ** 3)
            if free_gb < 1.0:
                self.logger.critical(f"磁盘空间不足: 仅剩 {free_gb:.2f} GB")
                return False
            return True
        except Exception as e:
            self.logger.error(f"检查磁盘空间失败: {e}")
            return True

    def save_to_parquet(self):
        """保存数据到Parquet文件"""
        if not self._check_disk_space():
            self.logger.error("磁盘空间不足，跳过本次保存")
            return

        now_utc = datetime.now(timezone.utc)
        current_date = now_utc.strftime("%Y%m%d")
        current_hour = now_utc.strftime("%H")
        saved_count = 0

        for symbol in self.symbols:
            records = self._pop_records(symbol)
            if not records:
                continue

            try:
                df = pd.DataFrame(records)
                symbol_dir = self.data_dir / symbol / current_date
                symbol_dir.mkdir(parents=True, exist_ok=True)
                file_path = symbol_dir / f"funding_rate_{current_hour}.parquet"

                table = pa.Table.from_pandas(df, schema=self.schema)
                del df

                if file_path.exists():
                    existing_table = pq.read_table(file_path)
                    table = pa.concat_tables([existing_table, table])

                pq.write_table(table, file_path, compression='snappy')
                saved_count += len(records)
                del table

            except MemoryError as e:
                self.logger.critical(f"内存不足，无法保存 {symbol} 资金费率: {e}")
            except Exception as e:
                self.logger.error(f"保存 {symbol} 数据失败: {e}", exc_info=True)
                self._requeue_records(symbol, records)

        self.logger.info(f"已保存 {saved_count} 条资金费率记录")

    def auto_save_loop(self):
        """自动保存循环"""
        while self.running:
            time.sleep(self.save_interval)
            try:
                self.save_to_parquet()
            except Exception as e:
                self.logger.error(f"自动保存失败: {e}", exc_info=True)

    def start(self):
        """启动采集器"""
        self.running = True

        self.logger.info("启动资金费率采集器...")
        self.logger.info(f"交易对: {', '.join(self.symbols)}")

        # 启动获取线程
        self.fetch_thread = threading.Thread(target=self.fetch_loop, name="funding_fetch")
        self.fetch_thread.daemon = True
        self.fetch_thread.start()

        # 启动保存线程
        self.auto_save_thread = threading.Thread(target=self.auto_save_loop, name="funding_save")
        self.auto_save_thread.daemon = True
        self.auto_save_thread.start()

        self.logger.info("资金费率采集器已启动")

    def stop(self):
        """停止采集器"""
        self.logger.info("正在停止资金费率采集器...")
        self.running = False

        # 等待线程结束
        if self.fetch_thread and self.fetch_thread.is_alive():
            self.fetch_thread.join(timeout=10)
            if self.fetch_thread.is_alive():
                self.logger.warning("获取线程未能在10秒内结束")

        if self.auto_save_thread and self.auto_save_thread.is_alive():
            self.auto_save_thread.join(timeout=10)
            if self.auto_save_thread.is_alive():
                self.logger.warning("保存线程未能在10秒内结束")

        # 保存剩余数据
        try:
            self.save_to_parquet()
        except Exception as e:
            self.logger.error(f"保存剩余数据失败: {e}", exc_info=True)

        self.session.close()
        self.logger.info("资金费率采集器已停止")
