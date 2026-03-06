"""Binance现货市场Orderbook采集器"""
import time
import pyarrow as pa
from base_orderbook_collector import BaseOrderbookCollector
from config import DEPTH_LEVEL


class SpotOrderbookCollector(BaseOrderbookCollector):
    """现货市场Orderbook采集器，处理depth snapshot格式"""

    def _build_schema(self):
        """构建Spot Orderbook Schema (85列)"""
        schema_fields = [
            ('timestamp', pa.int64()),
            ('symbol', pa.string()),
            ('market_type', pa.string()),
            ('first_update_id', pa.int64()),  # 新增字段
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
        # Spot格式：完整快照，不包含事件类型
        if 'lastUpdateId' not in data:
            self.logger.warning(f"未知消息格式: {list(data.keys())}")
            return None

        # 修复：使用服务器事件时间E而非本地时间
        timestamp = data.get('E', int(time.time() * 1000))
        bids = data['bids']
        asks = data['asks']
        last_update_id = data['lastUpdateId']
        # Spot没有单独的first_update_id，使用lastUpdateId
        first_update_id = last_update_id

        # 构建展开的orderbook记录
        orderbook_record = {
            'timestamp': timestamp,
            'symbol': symbol,
            'market_type': self.market_type,
            'first_update_id': first_update_id,
        }

        # 展开bids（买单）
        bids = bids[:DEPTH_LEVEL]
        for i in range(DEPTH_LEVEL):
            if i < len(bids):
                orderbook_record[f'bid{i+1}_price'] = float(bids[i][0])
                orderbook_record[f'bid{i+1}_qty'] = float(bids[i][1])
            else:
                # 如果不足20档，填充0
                orderbook_record[f'bid{i+1}_price'] = 0.0
                orderbook_record[f'bid{i+1}_qty'] = 0.0

        # 展开asks（卖单）
        asks = asks[:DEPTH_LEVEL]
        for i in range(DEPTH_LEVEL):
            if i < len(asks):
                orderbook_record[f'ask{i+1}_price'] = float(asks[i][0])
                orderbook_record[f'ask{i+1}_qty'] = float(asks[i][1])
            else:
                # 如果不足20档，填充0
                orderbook_record[f'ask{i+1}_price'] = 0.0
                orderbook_record[f'ask{i+1}_qty'] = 0.0

        orderbook_record['last_update_id'] = last_update_id

        return orderbook_record

    def _get_stream_name(self, symbol):
        """获取Spot WebSocket stream名称"""
        return f"{symbol.lower()}@depth20@100ms"
