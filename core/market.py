import asyncio
from utils.ws import BinanceWebSocket
from core.state import shared_state
from utils.config_loader import get_config
from decimal import Decimal, ROUND_HALF_UP

class MarketDataWorker:
    """
    行情订阅与处理模块：
    - 通过 BinanceWebSocket 订阅 bookTicker
    - 实时计算中间价并写入 shared_state
    - 便于后续扩展多币种/多行情类型
    - 金额、价格、数量全部用 Decimal，避免 float 精度误差
    """
    def __init__(self, symbol: str, env: str = "testnet"):
        self.symbol = symbol
        self.env = env
        self.ws = BinanceWebSocket(symbol, env)
        self._running = False
        self._last_printed_mid = None

    async def run(self):
        """启动行情订阅主循环"""
        await self.ws.connect()
        await self.ws.subscribe_bookticker()
        self._running = True
        print(f"[MarketDataWorker] 已连接 {self.env}，订阅 {self.symbol}@bookTicker")
        try:
            async for msg in self.ws.listen():
                self.handle_message(msg)
        except Exception as e:
            print(f"[MarketDataWorker] 运行异常: {e}")
        finally:
            await self.ws.close()
            self._running = False

    def handle_message(self, msg):
        """处理 bookTicker 消息，计算中间价并写入 shared_state（Decimal 精度）"""
        try:
            bid = Decimal(str(msg.get('b', '0')))
            ask = Decimal(str(msg.get('a', '0')))
            if bid > 0 and ask > 0:
                mid = ((bid + ask) / 2).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
                shared_state.safe_update(mark_price=float(mid))
                # 只在价格变动大于1时打印
                if self._last_printed_mid is None or abs(mid - self._last_printed_mid) >= Decimal('1'):
                    print(f"[MarketDataWorker] 中间价更新: {mid}")
                    self._last_printed_mid = mid
        except Exception as e:
            print(f"[MarketDataWorker] 消息处理异常: {e}, msg={msg}")
