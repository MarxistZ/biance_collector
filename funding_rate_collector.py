"""合约市场资金费率采集器"""
import time
import threading
import shutil
from datetime import datetime
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
        self.fetch_interval = 10  # 每10秒获取一次
        self.save_interval = 60  # 每60秒保存一次

        self.fetch_thread = None
        self.save_thread = None
        self.auto_save_thread = None

        # 内存保护阈值
        self.max_records_per_symbol = 10000

    def fetch_funding_rate(self, symbol):
        """获取单个交易对的资金费率和相关数据"""
        try:
            # 获取资金费率
            premium_url = f"{self.api_base}/fapi/v1/premiumIndex?symbol={symbol}"
            premium_resp = requests.get(premium_url, timeout=5)

            # 处理HTTP错误
            if premium_resp.status_code == 429:
                self.logger.warning(f"API速率限制 (429)，等待60秒")
                time.sleep(60)
                return None
            elif premium_resp.status_code == 418:
                self.logger.critical(f"IP被封禁 (418)，等待10分钟")
                time.sleep(600)
                return None
            elif premium_resp.status_code >= 400:
                self.logger.error(f"API请求失败 [{symbol}]: HTTP {premium_resp.status_code}")
                return None

            premium_data = premium_resp.json()

            # 获取24h交易量
            ticker_url = f"{self.api_base}/fapi/v1/ticker/24hr?symbol={symbol}"
            ticker_resp = requests.get(ticker_url, timeout=5)
            if ticker_resp.status_code != 200:
                self.logger.warning(f"获取24h交易量失败 [{symbol}]: HTTP {ticker_resp.status_code}")
                ticker_data = {}
            else:
                ticker_data = ticker_resp.json()

            # 获取未平仓合约量
            oi_url = f"{self.api_base}/fapi/v1/openInterest?symbol={symbol}"
            oi_resp = requests.get(oi_url, timeout=5)
            if oi_resp.status_code != 200:
                self.logger.warning(f"获取未平仓合约量失败 [{symbol}]: HTTP {oi_resp.status_code}")
                oi_data = {}
            else:
                oi_data = oi_resp.json()

            # 使用Binance服务器时间戳，确保与orderbook时间对齐
            server_time = int(premium_data.get('time', int(time.time() * 1000)))

            record = {
                'timestamp': server_time,
                'symbol': symbol,
                'funding_rate': float(premium_data.get('lastFundingRate', 0)),
                'mark_price': float(premium_data.get('markPrice', 0)),
                'index_price': float(premium_data.get('indexPrice', 0)),
                'next_funding_time': int(premium_data.get('nextFundingTime', 0)),
                'open_interest': float(oi_data.get('openInterest', 0)),
                'volume_24h': float(ticker_data.get('volume', 0))
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
            for symbol in self.symbols:
                if not self.running:
                    break

                record = self.fetch_funding_rate(symbol)
                if record:
                    self.funding_data[symbol].append(record)

                    # 内存保护
                    if len(self.funding_data[symbol]) > self.max_records_per_symbol:
                        self.logger.warning(f"{symbol} 资金费率数据超过 {self.max_records_per_symbol} 条")

                time.sleep(0.1)  # 避免请求过快

            time.sleep(self.fetch_interval)

    def check_disk_space(self):
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
        # 检查磁盘空间
        if not self.check_disk_space():
            self.logger.error("磁盘空间不足，跳过本次保存")
            return

        current_date = datetime.now().strftime("%Y%m%d")
        current_hour = datetime.now().strftime("%H")

        for symbol, records in self.funding_data.items():
            if not records:
                continue

            try:
                df = pd.DataFrame(records)

                # 文件路径: data/futures/BTCUSDT/20240307/funding_rate_14.parquet
                symbol_dir = self.data_dir / symbol / current_date
                symbol_dir.mkdir(parents=True, exist_ok=True)

                file_path = symbol_dir / f"funding_rate_{current_hour}.parquet"

                table = pa.Table.from_pandas(df, schema=self.schema)

                # 追加模式
                if file_path.exists():
                    existing_table = pq.read_table(file_path)
                    table = pa.concat_tables([existing_table, table])

                pq.write_table(table, file_path, compression='snappy')

                file_size = file_path.stat().st_size / 1024  # KB
                self.logger.info(f"已保存 {len(records)} 条资金费率记录到 {file_path} ({file_size:.1f} KB)")

                # 保存成功后才清空数据
                self.funding_data[symbol] = []

            except Exception as e:
                self.logger.error(f"保存 {symbol} 数据失败: {e}", exc_info=True)
                # 不清空数据，下次继续尝试保存

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

        self.logger.info("资金费率采集器已停止")
