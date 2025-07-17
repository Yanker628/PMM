import asyncio
from decimal import Decimal
from utils.http import BinanceRest
from core.state import shared_state
from utils.config_loader import get_config

class RiskController:
    """
    风控模块：
    - 定时检查当前持仓，若超出最大持仓限制，自动市价平仓并暂停策略
    - 依赖 shared_state、配置参数和 REST API
    - 结构清晰，便于扩展更多风控规则
    """
    def __init__(self, rest: BinanceRest, symbol: str, max_net_position: Decimal, logger=None, check_interval: int = 1):
        self.rest = rest
        self.symbol = symbol
        self.max_net_position = max_net_position
        self.check_interval = check_interval
        self._running = False
        self.logger = logger

    async def run(self):
        """主循环：定时检查持仓并风控"""
        self._running = True
        while self._running:
            try:
                await self.check_and_risk_control()
            except Exception as e:
                print(f"[RiskController] 风控检查异常: {e}")
            await asyncio.sleep(self.check_interval)

    async def check_and_risk_control(self):
        """检查持仓，超限则平仓并暂停策略"""
        from utils.config_loader import get_config
        config = get_config()
        initial_capital = Decimal(str(config.yaml.get("initial_capital", 200)))
        max_net_position_ratio = Decimal(str(config.yaml.get("max_net_position_ratio", 0.5)))
        mark_price = Decimal(str(shared_state.mark_price or 1))
        # 正确币本位最大持仓（不做整数量化）
        max_net_position = (initial_capital * max_net_position_ratio) / mark_price
        position = self.get_position()
        print(f"[RiskController] 当前持仓: {position}, 最大允许: {max_net_position}")
        if abs(position) > max_net_position:
            print("[RiskController] 持仓超限，执行市价平仓并暂停策略！")
            if self.logger:
                self.logger.log_event(
                    event_type="risk_limit_exceeded",
                    details="持仓超限，触发风控",
                    extra={"position": float(position), "max_net_position": float(max_net_position)}
                )
            self.close_position()
            shared_state.strategy_paused = True

    def get_position(self) -> Decimal:
        """查询当前净持仓，优先用REST接口，异常时fallback到shared_state"""
        try:
            pos_info = self.rest.get_position_info(self.symbol)
            position_amt = Decimal(str(pos_info.get("positionAmt", "0")))
            return position_amt
        except Exception as e:
            print(f"[RiskController] 获取真实持仓失败，使用本地状态: {e}")
            return Decimal(str(shared_state.position))

    def close_position(self):
        """真实市价平仓，失败自动重试，最多5次，未归零则暂停策略"""
        position = self.get_position()
        if position == 0:
            print("[RiskController] 当前无持仓，无需平仓。")
            if self.logger:
                self.logger.log_event(
                    event_type="no_position",
                    details="当前无持仓，无需平仓。",
                    extra={}
                )
            return
        side = "SELL" if position > 0 else "BUY"
        qty = abs(position)
        max_retry = 5
        for attempt in range(1, max_retry + 1):
            print(f"[RiskController] 第{attempt}次市价{side}平仓，数量: {qty}")
            try:
                self.rest.place_order(self.symbol, side=side, quantity=qty, order_type="MARKET")
                import time
                time.sleep(1)
                new_position = self.get_position()
                if abs(new_position) < 1e-8:
                    shared_state.position = 0
                    print(f"[RiskController] 平仓成功，真实仓位已归零。共尝试{attempt}次。")
                    if self.logger:
                        self.logger.log_event(
                            event_type="forced_liquidation",
                            details=f"市价{side}平仓成功，数量: {qty}，共尝试{attempt}次",
                            extra={"side": side, "qty": float(qty), "attempt": attempt}
                        )
                    return
                else:
                    print(f"[RiskController] 平仓后真实仓位未归零，当前: {new_position}")
                    if self.logger:
                        self.logger.log_event(
                            event_type="liquidation_retry",
                            details=f"第{attempt}次平仓后仓位未归零，当前: {new_position}",
                            extra={"side": side, "qty": float(qty), "remain_position": float(new_position), "attempt": attempt}
                        )
            except Exception as e:
                print(f"[RiskController] 平仓异常: {e}")
                if self.logger:
                    self.logger.log_event(
                        event_type="risk_error",
                        details=f"第{attempt}次平仓异常: {e}",
                        extra={"side": side, "qty": float(qty), "attempt": attempt}
                    )
        # 多次重试后仍未归零
        print(f"[RiskController] 多次平仓失败，真实仓位仍未归零，暂停策略！")
        shared_state.strategy_paused = True
        if self.logger:
            self.logger.log_event(
                event_type="liquidation_failed",
                details=f"多次平仓失败，真实仓位仍未归零，暂停策略！最后仓位: {new_position}",
                extra={"side": side, "qty": float(qty), "remain_position": float(new_position), "attempt": max_retry}
            )

    def stop(self):
        self._running = False
