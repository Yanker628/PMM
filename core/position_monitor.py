import asyncio
from decimal import Decimal

class PositionMonitorWorker:
    def __init__(self, rest, symbol, interval=10):
        self.rest = rest
        self.symbol = symbol
        self.interval = interval
        self._running = False

    async def run(self):
        self._running = True
        while self._running:
            try:
                pos_info = self.rest.get_position_info(self.symbol)
                position_amt = Decimal(str(pos_info.get("positionAmt", "0")))
                entry_price = Decimal(str(pos_info.get("entryPrice", "0")))
                unrealized_pnl = Decimal(str(pos_info.get("unRealizedProfit", "0")))
                mark_price = Decimal(str(pos_info.get("markPrice", "0")))
                print(f"[PositionMonitor] 仓位: {position_amt} | 持仓均价: {entry_price} | 最新价: {mark_price} | 未实现盈亏: {unrealized_pnl}")
            except Exception as e:
                print(f"[PositionMonitor] 获取仓位信息失败: {e}")
            await asyncio.sleep(self.interval)

    def stop(self):
        self._running = False 