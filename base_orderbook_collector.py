"""Binance Orderbook采集器抽象基类"""
import json
import time
import threading
import shutil
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from pathlib import Path
import websocket
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
from logger_config import setup_logger


class BaseOrderbookCollector(ABC):
    """Orderbook采集器抽象基类，提供WebSocket管理、重连、健康检查、自动保存等共享功能"""

    def __init__(self, symbols, ws_url, data_dir, market_type):
        self.symbols = symbols
        self.ws_url = ws_url
        self.data_dir = Path(data_dir)
        self.market_type = market_type
        self.data_dir.mkdir(parents=True, exist_ok=True)

        # 设置日志
        self.logger = setup_logger(f"orderbook_{market_type}")

        self.orderbook_data = {symbol: [] for symbol in symbols}
        self.ws_connections = {}
        self.ws_to_symbol = {}
        self.ws_threads = {}
        self.running = False
        self.data_lock = threading.Lock()

        # WebSocket重连配置
        self.max_reconnect_attempts = 10
        self.reconnect_delay = 5  # 初始延迟5秒
        self.max_reconnect_delay = 300  # 最大延迟5分钟
        self.reconnect_attempts = {symbol: 0 for symbol in symbols}
        self.reconnect_timers = {}

        # 健康监控
        self.last_data_time = {symbol: time.time() for symbol in symbols}
        self.connection_status = {symbol: 'disconnected' for symbol in symbols}

        # 构建schema（由子类实现）
        self.schema = self._build_schema()

        # 定时保存线程
        self.save_interval = 10  # 每10秒保存一次（1GB内存优化）
        self.auto_save_thread = None

        # 内存保护阈值
        self.max_records_per_symbol = 600  # 严格内存限制（1GB VPS）

    @abstractmethod
    def _build_schema(self):
        """构建PyArrow schema（由子类实现）"""
        pass

    @abstractmethod
    def _parse_message(self, data, symbol):
        """解析WebSocket消息并返回orderbook记录（由子类实现）"""
        pass

    @abstractmethod
    def _get_stream_name(self, symbol):
        """获取WebSocket stream名称（由子类实现）"""
        pass

    def _get_symbol_by_ws(self, ws):
        """根据WebSocket对象快速定位symbol"""
        symbol = self.ws_to_symbol.get(id(ws))
        if symbol:
            return symbol

        for sym, connection in self.ws_connections.items():
            if connection is ws:
                self.ws_to_symbol[id(ws)] = sym
                return sym
        return None

    def _expand_orderbook_side(self, record, side_name, levels, depth_level):
        """将买卖盘档位展开为固定列"""
        levels = levels[:depth_level]
        for i in range(depth_level):
            if i < len(levels):
                record[f"{side_name}{i + 1}_price"] = float(levels[i][0])
                record[f"{side_name}{i + 1}_qty"] = float(levels[i][1])
            else:
                record[f"{side_name}{i + 1}_price"] = 0.0
                record[f"{side_name}{i + 1}_qty"] = 0.0

    def _pop_records(self, symbol):
        """原子性取出待保存数据，避免保存线程与回调线程并发冲突"""
        with self.data_lock:
            records = self.orderbook_data[symbol]
            if not records:
                return []
            self.orderbook_data[symbol] = []
            return records

    def _requeue_records(self, symbol, records):
        """保存失败时回填数据，避免临时写入异常导致数据丢失"""
        if not records:
            return
        with self.data_lock:
            self.orderbook_data[symbol] = records + self.orderbook_data[symbol]

    def on_message(self, ws, message):
        """处理WebSocket消息"""
        try:
            data = json.loads(message)
            symbol = self._get_symbol_by_ws(ws)

            if not symbol:
                self.logger.warning("无法识别WebSocket连接对应的symbol")
                return

            # 调用子类实现的解析方法
            orderbook_record = self._parse_message(data, symbol)
            if not orderbook_record:
                return

            with self.data_lock:
                self.orderbook_data[symbol].append(orderbook_record)
                buffer_size = len(self.orderbook_data[symbol])
            self.last_data_time[symbol] = time.time()

            if buffer_size == self.max_records_per_symbol + 1:
                self.logger.warning(f"{symbol} 内存数据超过 {self.max_records_per_symbol} 条，可能存在保存延迟")

        except Exception as e:
            self.logger.error(f"处理消息错误: {e}", exc_info=True)

    def on_error(self, ws, error):
        """处理WebSocket错误"""
        symbol = self._get_symbol_by_ws(ws)

        error_str = str(error)
        self.logger.error(f"WebSocket错误 [{symbol}]: {error_str}")

        # 区分错误类型
        if "Connection" in error_str or "timeout" in error_str.lower():
            # 网络错误，触发重连
            if symbol:
                self.connection_status[symbol] = 'error'
                self.logger.info(f"检测到网络错误，将尝试重连 {symbol}")
        else:
            # 协议错误，记录但继续运行
            self.logger.warning(f"协议错误 [{symbol}]: {error_str}")

    def on_close(self, ws, close_status_code, close_msg):
        """WebSocket关闭"""
        symbol = self._get_symbol_by_ws(ws)

        self.logger.warning(f"WebSocket连接关闭 [{symbol}]: {close_status_code} - {close_msg}")

        if symbol:
            self.connection_status[symbol] = 'closed'
            # 如果采集器仍在运行，尝试重连
            if self.running:
                self.reconnect_websocket(symbol)

    def on_open(self, ws):
        """WebSocket连接建立"""
        symbol = self._get_symbol_by_ws(ws)

        if symbol:
            self.connection_status[symbol] = 'connected'
            self.reconnect_attempts[symbol] = 0  # 重置重连计数
            self.logger.info(f"WebSocket连接已建立 [{symbol}] - {self.market_type}")

    def reconnect_websocket(self, symbol):
        """重连WebSocket"""
        if self.reconnect_attempts[symbol] >= self.max_reconnect_attempts:
            self.logger.critical(f"{symbol} 达到最大重连次数 ({self.max_reconnect_attempts})，停止重连")
            return

        self.reconnect_attempts[symbol] += 1
        # 指数退避策略
        delay = min(self.reconnect_delay * (2 ** (self.reconnect_attempts[symbol] - 1)),
                   self.max_reconnect_delay)

        self.logger.info(f"将在 {delay} 秒后重连 {symbol} (尝试 {self.reconnect_attempts[symbol]}/{self.max_reconnect_attempts})")

        # 使用Timer实现延迟重连
        timer = threading.Timer(delay, self._do_reconnect, args=[symbol])
        self.reconnect_timers[symbol] = timer
        timer.start()

    def _do_reconnect(self, symbol):
        """执行重连"""
        if not self.running:
            return

        self.logger.info(f"正在重连 {symbol}...")
        try:
            # 关闭旧连接
            if symbol in self.ws_connections:
                try:
                    self.ws_connections[symbol].close()
                except Exception:
                    pass

            # 建立新连接
            self.connect_symbol(symbol)
        except Exception as e:
            self.logger.error(f"重连 {symbol} 失败: {e}", exc_info=True)
            # 继续尝试重连
            self.reconnect_websocket(symbol)

    def connect_symbol(self, symbol):
        """连接单个交易对的WebSocket"""
        stream_name = self._get_stream_name(symbol)
        ws_url = f"{self.ws_url}/{stream_name}"

        ws = websocket.WebSocketApp(
            ws_url,
            on_message=self.on_message,
            on_error=self.on_error,
            on_close=self.on_close,
            on_open=self.on_open
        )

        old_ws = self.ws_connections.get(symbol)
        if old_ws is not None:
            self.ws_to_symbol.pop(id(old_ws), None)

        self.ws_connections[symbol] = ws
        self.ws_to_symbol[id(ws)] = symbol

        # 在新线程中运行
        thread = threading.Thread(target=ws.run_forever, name=f"ws_{symbol}")
        thread.daemon = True
        thread.start()
        self.ws_threads[symbol] = thread

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
                file_path = symbol_dir / f"orderbook_{current_hour}.parquet"

                table = pa.Table.from_pandas(df, schema=self.schema)
                del df

                if file_path.exists():
                    existing_table = pq.read_table(file_path)
                    table = pa.concat_tables([existing_table, table])

                pq.write_table(table, file_path, compression='snappy')
                saved_count += len(records)
                del table

            except MemoryError as e:
                self.logger.critical(f"内存不足，无法保存 {symbol}: {e}")
            except Exception as e:
                self.logger.error(f"保存 {symbol} 数据失败: {e}", exc_info=True)
                self._requeue_records(symbol, records)

        self.logger.info(f"已保存 {saved_count} 条记录")

    def auto_save_loop(self):
        """自动保存循环，包含健康检查"""
        last_health_check = time.time()
        health_check_interval = 600  # 每10分钟输出一次健康状态

        while self.running:
            time.sleep(self.save_interval)

            try:
                self.save_to_parquet()

                # 健康检查
                current_time = time.time()
                if current_time - last_health_check >= health_check_interval:
                    self.health_check()
                    last_health_check = current_time

            except Exception as e:
                self.logger.error(f"自动保存失败: {e}", exc_info=True)

    def health_check(self):
        """健康检查：检测长时间无数据的连接"""
        current_time = time.time()
        for symbol in self.symbols:
            time_since_last_data = current_time - self.last_data_time[symbol]

            if time_since_last_data > 600:  # 10分钟无数据
                self.logger.warning(f"{symbol} 已 {time_since_last_data:.0f} 秒无数据，尝试重连")
                if symbol in self.ws_connections:
                    try:
                        self.ws_connections[symbol].close()
                    except Exception:
                        pass
                self.reconnect_websocket(symbol)
            elif time_since_last_data > 300:  # 5分钟无数据
                self.logger.warning(f"{symbol} 已 {time_since_last_data:.0f} 秒无数据")

        # 输出统计信息
        with self.data_lock:
            total_records = sum(len(records) for records in self.orderbook_data.values())
        self.logger.info(f"健康检查 - 内存中共 {total_records} 条记录，连接状态: {self.connection_status}")

    def start(self):
        """启动采集器"""
        self.running = True

        self.logger.info(f"启动 {self.market_type} 市场采集器...")
        self.logger.info(f"交易对: {', '.join(self.symbols)}")

        # 连接所有交易对
        for symbol in self.symbols:
            self.connect_symbol(symbol)
            time.sleep(0.1)  # 避免连接过快

        # 启动自动保存线程
        self.auto_save_thread = threading.Thread(target=self.auto_save_loop, name=f"auto_save_{self.market_type}")
        self.auto_save_thread.daemon = True
        self.auto_save_thread.start()

        self.logger.info(f"{self.market_type} 采集器已启动")

    def stop(self):
        """停止采集器"""
        self.logger.info(f"正在停止 {self.market_type} 采集器...")
        self.running = False

        # 取消所有重连定时器
        for timer in list(self.reconnect_timers.values()):
            if timer.is_alive():
                timer.cancel()

        # 关闭所有WebSocket连接
        for symbol, ws in list(self.ws_connections.items()):
            try:
                ws.close()
                self.ws_to_symbol.pop(id(ws), None)
                self.logger.debug(f"已关闭 {symbol} WebSocket连接")
            except Exception as e:
                self.logger.warning(f"关闭 {symbol} WebSocket失败: {e}")

        # 等待自动保存线程结束
        if self.auto_save_thread and self.auto_save_thread.is_alive():
            self.auto_save_thread.join(timeout=10)
            if self.auto_save_thread.is_alive():
                self.logger.warning("自动保存线程未能在10秒内结束")

        # 等待WebSocket线程结束
        for symbol, thread in self.ws_threads.items():
            if thread.is_alive():
                thread.join(timeout=5)
                if thread.is_alive():
                    self.logger.warning(f"{symbol} WebSocket线程未能在5秒内结束")

        # 保存剩余数据
        try:
            self.save_to_parquet()
        except Exception as e:
            self.logger.error(f"保存剩余数据失败: {e}", exc_info=True)

        self.logger.info(f"{self.market_type} 采集器已停止")
