import asyncio
import signal
from utils.config_loader import get_config
from utils.http import BinanceRest
from core.market import MarketDataWorker
from core.order import OrderManager
from core.state import shared_state
from decimal import Decimal
from core.risk import RiskController
from core.logger import LoggerWorker
from core.position_monitor import PositionMonitorWorker

async def main():
    config = get_config()
    api_key = config.env.get("BINANCE_API_KEY") or ""
    secret_key = config.env.get("BINANCE_SECRET_KEY") or ""
    env = config.env.get("EXCHANGE_ENV", "testnet")
    symbol = config.get("symbol", "BTCUSDT")
    order_cfg = config.yaml.get("order_config", {})
    levels = int(order_cfg.get("levels", 3))
    qty_per_order_usdt = Decimal(str(order_cfg.get("quantity_per_order_usdt", 10)))
    price_offset_percent = Decimal(str(order_cfg.get("price_offset_percent", 0.25)))
    refresh_interval = int(config.yaml.get("refresh_config", {}).get("orderbook_refresh_interval", 5))
    # 风控参数
    max_net_position_ratio = Decimal(str(config.yaml.get("max_net_position_ratio", 0.5)))
    initial_capital = Decimal(str(config.yaml.get("initial_capital", 200)))
    # 启动行情订阅
    market_worker = MarketDataWorker(symbol, env)
    # 启动挂单管理（数量按最新中间价动态计算）
    rest = BinanceRest(api_key, secret_key, env)
    # 启动日志采集
    logging_cfg = config.yaml.get("logging", {})
    log_dir = logging_cfg.get("log_directory", "./logs")
    log_to_csv = logging_cfg.get("log_to_csv", True)
    log_level = logging_cfg.get("log_level", "info")
    instance_id = "mvp_v1"
    logger_worker = LoggerWorker(rest, log_dir, log_to_csv, log_level, symbol, instance_id, env)
    # 计算最大持仓
    mark_price = Decimal(str(shared_state.mark_price or 1))
    max_net_position = (initial_capital * max_net_position_ratio / mark_price).quantize(Decimal('1'))
    risk_controller = RiskController(rest, symbol, max_net_position, logger=logger_worker)

    async def order_manager_wrapper():
        # 等待有效中间价
        while shared_state.mark_price <= 0:
            print("[Main] 等待行情模块推送有效中间价...")
            await asyncio.sleep(1)
        # 动态计算下单数量（按USDT金额/最新中间价）
        qty_per_order = (qty_per_order_usdt / Decimal(str(shared_state.mark_price))).quantize(Decimal('0.001'))
        manager = OrderManager(rest, symbol, levels, qty_per_order, price_offset_percent, refresh_interval)
        await manager.run()

    position_monitor = PositionMonitorWorker(rest, symbol, interval=10)

    tasks = [
        asyncio.create_task(market_worker.run()),
        asyncio.create_task(order_manager_wrapper()),
        asyncio.create_task(logger_worker.run()),
        asyncio.create_task(position_monitor.run()),
        asyncio.create_task(risk_controller.run())
    ]
    # 信号处理
    stop_flag = {"stop": False}
    def handle_exit(*args):
        print("\n[Main] 收到退出信号，准备清理资源...")
        stop_flag["stop"] = True
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            asyncio.get_event_loop().add_signal_handler(sig, handle_exit)
        except NotImplementedError:
            pass  # Windows兼容
    try:
        while not stop_flag["stop"]:
            await asyncio.sleep(1)
    except Exception as e:
        print(f"[Main] 程序异常: {e}")
    finally:
        print("[Main] 停止各模块...")
        if hasattr(risk_controller, 'stop'):
            risk_controller.stop()
        print("[Main] 撤销所有挂单...")
        try:
            rest.cancel_all_orders(symbol)
            print("[Main] 挂单已全部撤销。")
        except Exception as e:
            print(f"[Main] 撤销挂单异常: {e}")
        print("[Main] 平掉所有持仓...")
        try:
            risk_controller.close_position()
        except Exception as e:
            print(f"[Main] 平仓异常: {e}")
        print("[Main] 取消所有异步任务...")
        for task in tasks:
            task.cancel()
        print("[Main] 清理完成，安全退出。")
        if hasattr(logger_worker, 'stop'):
            logger_worker.stop()
        if hasattr(position_monitor, 'stop'):
            position_monitor.stop()

if __name__ == "__main__":
    asyncio.run(main())
