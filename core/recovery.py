import asyncio
import traceback

class RecoveryManager:
    """
    容错与异常监控模块：
    - 监控各核心模块运行状态，发现异常自动重启或恢复
    - 结构清晰，便于扩展更多容错策略
    """
    def __init__(self, workers: dict, check_interval: int = 5):
        """
        workers: dict，格式如 {"market": MarketDataWorker实例, ...}
        check_interval: 监控间隔秒数
        """
        self.workers = workers
        self.check_interval = check_interval
        self._running = False
        self._tasks = {}

    async def run(self):
        """主循环：定时监控并恢复异常模块"""
        self._running = True
        # 启动所有worker
        for name, worker in self.workers.items():
            self._tasks[name] = asyncio.create_task(self._run_worker(name, worker))
        while self._running:
            await asyncio.sleep(self.check_interval)
            self.monitor_modules()

    async def _run_worker(self, name, worker):
        """包装worker的run方法，捕获异常自动重启"""
        while self._running:
            try:
                await worker.run()
            except Exception as e:
                print(f"[RecoveryManager] {name} 异常: {e}\n{traceback.format_exc()}")
                print(f"[RecoveryManager] 尝试重启 {name} ...")
                await asyncio.sleep(2)
                # 自动重启
                continue
            break

    def monitor_modules(self):
        """检查各模块状态（可扩展更复杂健康检查）"""
        for name, task in self._tasks.items():
            if task.done() and not task.cancelled():
                print(f"[RecoveryManager] 检测到 {name} 已退出，尝试重启...")
                # 这里可实现更复杂的重启逻辑

    def stop(self):
        self._running = False
        for task in self._tasks.values():
            task.cancel()
