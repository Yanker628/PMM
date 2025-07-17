import asyncio
import csv
import os
from datetime import datetime
from core.state import shared_state
from utils.config_loader import get_config
import json

class LoggerWorker:
    """
    日志采集与指标记录模块：
    - 定时采集关键指标，写入CSV文件
    - 结构清晰，便于扩展更多指标
    """
    def __init__(self, rest, log_dir: str, log_to_csv: bool, log_level: str, symbol: str, instance_id: str, env: str, interval: int = 1):
        self.log_dir = log_dir
        self.log_to_csv = log_to_csv
        self.log_level = log_level
        self.symbol = symbol
        self.instance_id = instance_id
        self.env = env
        self.interval = interval
        self.csv_file = None
        self.csv_writer = None
        self.csv_path = None
        self._prepare_csv()
        self._running = False
        self.rest = rest

    def _prepare_csv(self):
        if not self.log_to_csv:
            return
        os.makedirs(self.log_dir, exist_ok=True)
        today = datetime.now().strftime("%Y%m%d")
        self.csv_path = os.path.join(self.log_dir, f"metrics-{today}.csv")
        file_exists = os.path.isfile(self.csv_path)
        self.csv_file = open(self.csv_path, "a", newline="", encoding="utf-8")
        self.csv_writer = csv.DictWriter(self.csv_file, fieldnames=[
            "timestamp", "instance_id", "env", "metric_name", "value", "unit", "symbol", "side", "level", "sub_type", "details"
        ])
        if not file_exists:
            self.csv_writer.writeheader()

    def _prepare_event_csv(self):
        self.event_csv_path = os.path.join(self.log_dir, f"events-{datetime.now().strftime('%Y%m%d')}.csv")
        file_exists = os.path.isfile(self.event_csv_path)
        self.event_csv_file = open(self.event_csv_path, "a", newline="", encoding="utf-8")
        self.event_csv_writer = csv.DictWriter(self.event_csv_file, fieldnames=[
            "timestamp", "instance_id", "env", "event_type", "symbol", "details", "extra"
        ])
        if not file_exists:
            self.event_csv_writer.writeheader()

    def log_event(self, event_type: str, details: str, extra: dict | None = None):
        """结构化写入风控/异常等事件日志"""
        if not self.log_to_csv:
            return
        if not hasattr(self, 'event_csv_writer') or self.event_csv_writer is None:
            self._prepare_event_csv()
        now = datetime.now().isoformat()
        row = {
            "timestamp": now,
            "instance_id": self.instance_id,
            "env": self.env,
            "event_type": event_type,
            "symbol": self.symbol,
            "details": details,
            "extra": json.dumps(extra or {}, ensure_ascii=False)
        }
        print(f"[LoggerWorker] 事件日志: {row}")
        self.event_csv_writer.writerow(row)
        self.event_csv_file.flush()

    async def run(self):
        """主循环：定时采集并写入日志"""
        self._running = True
        while self._running:
            try:
                metrics = self.collect_metrics()
                if self.log_to_csv and self.csv_writer and self.csv_file:
                    self.csv_writer.writerow(metrics)
                    self.csv_file.flush()
                if self.log_level == "debug":
                    print(f"[LoggerWorker] 采集指标: {metrics}")
            except Exception as e:
                print(f"[LoggerWorker] 日志采集异常: {e}")
            await asyncio.sleep(self.interval)

    def collect_metrics(self) -> dict:
        """采集账户净值、盈亏、持仓等关键指标"""
        now = datetime.now().isoformat()
        mark_price = shared_state.mark_price
        try:
            account_info = self.rest.get_account_info()
            equity = account_info.get("totalWalletBalance") or account_info.get("totalMarginBalance")
            realized_pnl = account_info.get("totalUnrealizedProfit")  # 实际应为已实现盈亏，Binance接口需区分
            # 兼容不同字段
            if "totalRealizedProfit" in account_info:
                realized_pnl = account_info["totalRealizedProfit"]
            position_info = self.rest.get_position_info(self.symbol)
            position_amt = position_info.get("positionAmt", "0")
            unrealized_pnl = position_info.get("unRealizedProfit", "0")
        except Exception as e:
            equity = realized_pnl = unrealized_pnl = position_amt = None
            print(f"[LoggerWorker] 采集账户信息异常: {e}")
        return {
            "timestamp": now,
            "instance_id": self.instance_id,
            "env": self.env,
            "metric_name": "account_metrics",
            "value": equity,
            "unit": "usdt",
            "symbol": self.symbol,
            "side": "-",
            "level": "-",
            "sub_type": "-",
            "details": f"realized_pnl={realized_pnl},unrealized_pnl={unrealized_pnl},position={position_amt},mark_price={mark_price}"
        }

    def stop(self):
        self._running = False
        if self.csv_file:
            self.csv_file.close()
        if hasattr(self, 'event_csv_file') and self.event_csv_file:
            self.event_csv_file.close()
