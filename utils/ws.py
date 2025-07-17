import asyncio
import websockets
import json
from typing import Optional, Any

# Binance Future Testnet与实盘WebSocket地址
BINANCE_WS_URLS = {
    "testnet": "wss://stream.binancefuture.com/ws",  # Testnet
    # "mainnet": "wss://fstream.binance.com/ws",    # 实盘，后续支持
}

class BinanceWebSocket:
    """
    Binance Future WebSocket 封装，支持 testnet，预留 mainnet 切换接口。
    用法：
        ws = BinanceWebSocket(symbol="btcusdt", env="testnet")
        await ws.connect()
        await ws.subscribe_bookticker()
        async for msg in ws.listen():
            ...
    """
    def __init__(self, symbol: str, env: str = "testnet"):
        self.symbol = symbol.lower()
        self.env = env
        self.url = BINANCE_WS_URLS.get(env, BINANCE_WS_URLS["testnet"])
        self.ws: Optional[Any] = None  # 类型注解更宽松，兼容不同实现
        self._connected = False

    async def connect(self):
        """建立WebSocket连接"""
        self.ws = await websockets.connect(self.url)
        self._connected = True

    async def subscribe_bookticker(self):
        """订阅 bookTicker 行情"""
        if not self._connected or self.ws is None:
            raise RuntimeError("WebSocket 未连接，无法订阅 bookTicker")
        params = {
            "method": "SUBSCRIBE",
            "params": [f"{self.symbol}@bookTicker"],
            "id": 1
        }
        await self.ws.send(json.dumps(params))

    async def listen(self):
        """异步生成器，持续接收消息"""
        if not self._connected or self.ws is None:
            raise RuntimeError("WebSocket 未连接，无法监听消息")
        try:
            async for msg in self.ws:
                yield json.loads(msg)
        except Exception as e:
            self._connected = False
            raise RuntimeError(f"WebSocket 监听异常: {e}")

    async def close(self):
        """关闭WebSocket连接"""
        if self.ws:
            await self.ws.close()
            self._connected = False

    @property
    def connected(self):
        return self._connected
