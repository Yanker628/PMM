import asyncio
from decimal import Decimal, ROUND_DOWN
from utils.http import BinanceRest
from core.state import shared_state
from utils.config_loader import get_config

class OrderManager:
    """
    挂单管理模块：
    - 每N秒撤销所有挂单，自动挂3档限价单
    - 价格、数量用Decimal，精度严格控制
    - 依赖 shared_state 的中间价和配置参数
    - 便于后续扩展风控、容错等
    """
    def __init__(self, rest: BinanceRest, symbol: str, order_levels: int, qty_per_order: Decimal, price_offset_percent: Decimal, refresh_interval: int = 5):
        self.rest = rest
        self.symbol = symbol
        self.order_levels = order_levels
        self.qty_per_order = qty_per_order
        self.price_offset_percent = price_offset_percent
        self.refresh_interval = refresh_interval
        self._running = False
        # 自动获取币种精度参数
        info = rest.get_symbol_info(symbol)
        self.step_size = Decimal(info["step_size"])
        self.min_qty = Decimal(info["min_qty"])
        self.price_tick = Decimal(info["price_tick"])
        print(f"[OrderManager] {symbol} 精度参数: step_size={self.step_size}, min_qty={self.min_qty}, price_tick={self.price_tick}")

    async def run(self):
        """主循环：定时撤单并挂单"""
        self._running = True
        while self._running:
            try:
                await self.refresh_orders()
            except Exception as e:
                print(f"[OrderManager] 刷单异常: {e}")
            await asyncio.sleep(self.refresh_interval)

    async def refresh_orders(self):
        print("[OrderManager] 撤销所有挂单...")
        self.rest.cancel_all_orders(self.symbol)
        mid = Decimal(str(shared_state.mark_price)).quantize(self.price_tick, rounding=ROUND_DOWN)
        print(f"[OrderManager] 当前中间价: {mid}")
        # 获取币种精度和最小下单量
        info = self.rest.get_symbol_info(self.symbol)
        step_size = Decimal(info["step_size"])
        min_qty = Decimal(info["min_qty"])
        # 动态获取最大允许仓位
        from utils.config_loader import get_config
        config = get_config()
        initial_capital = Decimal(str(config.yaml.get("initial_capital", 200)))
        max_net_position_ratio = Decimal(str(config.yaml.get("max_net_position_ratio", 0.5)))
        mark_price = Decimal(str(shared_state.mark_price or 1))
        max_net_position = (initial_capital * max_net_position_ratio) / mark_price
        # 获取当前真实持仓
        try:
            current_position = self.rest.get_position_info(self.symbol).get("positionAmt", "0")
            current_position = Decimal(str(current_position))
        except Exception as e:
            print(f"[OrderManager] 获取当前持仓失败: {e}")
            current_position = Decimal("0")
        # 每次从yaml读取下单金额
        order_cfg = config.yaml.get("order_config", {})
        qty_per_order_usdt = Decimal(str(order_cfg.get("quantity_per_order_usdt", 100)))
        for level in range(1, self.order_levels + 1):
            offset = self.price_offset_percent * level / Decimal('100')
            tick_size = self.price_tick.normalize()
            buy_price = (mid * (Decimal('1') - offset)).quantize(tick_size, rounding=ROUND_DOWN)
            sell_price = (mid * (Decimal('1') + offset)).quantize(tick_size, rounding=ROUND_DOWN)
            # 换算币本位数量
            raw_qty = qty_per_order_usdt / mark_price
            order_qty = raw_qty.quantize(step_size, rounding=ROUND_DOWN)
            # 受最大允许仓位约束
            max_order_qty = max_net_position - abs(current_position)
            if order_qty > max_order_qty:
                order_qty = max_order_qty.quantize(step_size, rounding=ROUND_DOWN)
            # 检查最小下单量
            if order_qty < min_qty:
                print(f"[OrderManager] 档位{level}下单数量 {order_qty} 小于最小下单量 {min_qty}，跳过该档买卖单")
                continue
            print(f"[OrderManager] 挂买单: {buy_price}, 卖单: {sell_price}, 档位: {level}, 数量: {order_qty}")
            self.rest.place_order(self.symbol, side="BUY", quantity=order_qty, price=buy_price)
            self.rest.place_order(self.symbol, side="SELL", quantity=order_qty, price=sell_price)

    def stop(self):
        self._running = False
