from dataclasses import dataclass, field
from typing import Optional
import threading

@dataclass
class SharedState:
    """
    全局共享状态结构，供各模块异步读写。
    字段可根据业务需求扩展。
    """
    mark_price: float = 0.0           # 最新中间价
    position: float = 0.0             # 当前净持仓（张/币）
    strategy_paused: bool = False     # 策略是否暂停
    last_order_time: Optional[float] = None  # 上次挂单时间戳
    last_risk_check: Optional[float] = None  # 上次风控检查时间戳
    # 可扩展更多字段，如订单列表、账户余额等

    # 线程锁，保证多线程/协程安全（如需）
    _lock: threading.Lock = field(default_factory=threading.Lock, init=False, repr=False)

    def safe_update(self, **kwargs):
        """线程安全地批量更新状态字段"""
        with self._lock:
            for k, v in kwargs.items():
                setattr(self, k, v)

# 单例实例，供全局 import 使用
shared_state = SharedState()
