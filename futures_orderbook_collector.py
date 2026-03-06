"""Binance合约市场Orderbook采集器"""
import pyarrow as pa
from base_orderbook_collector import BaseOrderbookCollector
from config import DEPTH_LEVEL


class FuturesOrderbookCollector(BaseOrderbookCollector):
    """合约市场Orderbook采集器，处理depthUpdate格式"""

    def _build_schema(self):
        """构建Futures Orderbook Schema (87列)"""
        schema_fields = [
            ('timestamp', pa.int64()),
            ('symbol', pa.string()),
            ('market_type', pa.string()),
            ('transaction_time', pa.int64()),  # 新增：撮合引擎时间T
            ('first_update_id', pa.int64()),   # 新增：首个更新ID U
            ('prev_update_id', pa.int64()),    # 新增：前一个更新ID pu
        ]
        # 添加20档bid价格和数量
        for i in range(1, DEPTH_LEVEL + 1):
            schema_fields.append((f'bid{i}_price', pa.float64()))
            schema_fields.append((f'bid{i}_qty', pa.float64()))
        # 添加20档ask价格和数量
        for i in range(1, DEPTH_LEVEL + 1):
            schema_fields.append((f'ask{i}_price', pa.float64()))
            schema_fields.append((f'ask{i}_qty', pa.float64()))
        schema_fields.append(('last_update_id', pa.int64()))

        return pa.schema(schema_fields)

    def _parse_message(self, data, symbol):
        """解析Futures depthUpdate消息"""
        if data.get("e") != "depthUpdate":
            return None

        required_fields = ("E", "T", "U", "u", "pu", "b", "a")
        if any(field not in data for field in required_fields):
            self.logger.warning(f"Futures消息缺少关键字段 [{symbol}]: {list(data.keys())}")
            return None

        if not isinstance(data["b"], list) or not isinstance(data["a"], list):
            self.logger.warning(f"Futures档位格式异常 [{symbol}]")
            return None

        try:
            orderbook_record = {
                "timestamp": int(data["E"]),
                "symbol": symbol,
                "market_type": self.market_type,
                "transaction_time": int(data["T"]),
                "first_update_id": int(data["U"]),
                "prev_update_id": int(data["pu"]),
            }
            last_update_id = int(data["u"])
        except (TypeError, ValueError):
            self.logger.warning(f"Futures消息时间或更新ID格式异常 [{symbol}]")
            return None

        self._expand_orderbook_side(orderbook_record, "bid", data["b"], DEPTH_LEVEL)
        self._expand_orderbook_side(orderbook_record, "ask", data["a"], DEPTH_LEVEL)
        orderbook_record["last_update_id"] = last_update_id

        return orderbook_record

    def _get_stream_name(self, symbol):
        """获取Futures WebSocket stream名称"""
        return f"{symbol.lower()}@depth{DEPTH_LEVEL}@100ms"
