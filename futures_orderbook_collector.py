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
        # Futures格式：增量更新，包含事件类型
        if 'e' not in data or data['e'] != 'depthUpdate':
            self.logger.warning(f"未知消息格式: {list(data.keys())}")
            return None

        # 提取所有关键字段
        timestamp = data['E']                # 事件时间
        transaction_time = data['T']         # 撮合引擎时间
        first_update_id = data['U']          # 首个更新ID
        last_update_id = data['u']           # 最后更新ID
        prev_update_id = data['pu']          # 前一个更新ID
        bids = data['b']
        asks = data['a']

        # 构建展开的orderbook记录
        orderbook_record = {
            'timestamp': timestamp,
            'symbol': symbol,
            'market_type': self.market_type,
            'transaction_time': transaction_time,
            'first_update_id': first_update_id,
            'prev_update_id': prev_update_id,
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
        """获取Futures WebSocket stream名称"""
        return f"{symbol.lower()}@depth20@100ms"
