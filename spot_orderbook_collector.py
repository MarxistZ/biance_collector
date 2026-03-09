"""Binance现货市场Orderbook采集器"""
import time
import pyarrow as pa
from base_orderbook_collector import BaseOrderbookCollector
from config import DEPTH_LEVEL


class SpotOrderbookCollector(BaseOrderbookCollector):
    """现货市场Orderbook采集器，处理depth snapshot格式"""

    def _build_schema(self):
        """构建Spot Orderbook Schema (86列)"""
        schema_fields = [
            ('timestamp', pa.int64()),
            ('local_timestamp', pa.int64()),
            ('symbol', pa.string()),
            ('market_type', pa.string()),
            ('first_update_id', pa.int64()),
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
        """解析Spot depth snapshot消息"""
        required_fields = ("E", "lastUpdateId", "bids", "asks")
        if any(field not in data for field in required_fields):
            self.logger.warning(f"Spot消息缺少关键字段: {list(data.keys())}")
            return None

        if not isinstance(data["bids"], list) or not isinstance(data["asks"], list):
            self.logger.warning(f"Spot档位格式异常 [{symbol}]")
            return None

        try:
            timestamp = int(data["E"])
            last_update_id = int(data["lastUpdateId"])
        except (TypeError, ValueError):
            self.logger.warning(f"Spot消息时间或更新ID格式异常 [{symbol}]")
            return None
        first_update_id = last_update_id

        orderbook_record = {
            "timestamp": timestamp,
            "local_timestamp": int(time.time() * 1000),
            "symbol": symbol,
            "market_type": self.market_type,
            "first_update_id": first_update_id,
        }

        self._expand_orderbook_side(orderbook_record, "bid", data["bids"], DEPTH_LEVEL)
        self._expand_orderbook_side(orderbook_record, "ask", data["asks"], DEPTH_LEVEL)
        orderbook_record["last_update_id"] = last_update_id

        return orderbook_record

    def _get_stream_name(self, symbol):
        """获取Spot WebSocket stream名称"""
        return f"{symbol.lower()}@depth{DEPTH_LEVEL}@100ms"
