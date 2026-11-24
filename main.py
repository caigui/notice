import asyncio
import time
import signal
import sys
import logging
from datetime import datetime, timedelta
from new_stock_info import NewStockNotifier
from qdii_arbitrage_alert import QDIIQueryStrategy, EFTQueryStrategy, QdiiStrategyExecutor
from stock_exchange_alert import StockMonitor
from cb.convertible_bonds_alert import ConvertibleBondsMonitor
from stock_config import StockConfig
from us_etf_premium_alert import UsEtfPremiumMonitor
import date_utils


logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)  # Crucial: Get logger for this specific module

class CancellableTask:
    def __init__(self):
        self._is_cancelled = False
        self._last_error = None
        self._last_error_time = 0

    async def loop(self):
        while not self._is_cancelled:
            try:
                await self.run_task()
                await asyncio.sleep(1)  # Important: Await inside the loop
            except asyncio.CancelledError:
                self._is_cancelled = True
                logging.info(f"{self.__class__.__name__}: Task cancelled.")
                break
            except Exception as e:
                # 同一异常 5 分钟内只打一次完整堆栈，避免异常时每轮刷屏
                now = time.time()
                sig = (type(e).__name__, str(e)[:160])
                if sig != getattr(self, '_last_error', None) or \
                        now - getattr(self, '_last_error_time', 0) >= 300:
                    logging.error(f"{self.__class__.__name__}: An error occurred: {e}", exc_info=True)
                    self._last_error, self._last_error_time = sig, now
                await asyncio.sleep(10)

    async def run_task(self):
        """This method has to be implemented by the child class"""
        raise NotImplementedError()

    def cancel(self):
        self._is_cancelled = True

class CancellableStockMonitor(StockMonitor, CancellableTask):
    def __init__(self, config):
        StockMonitor.__init__(self, config)
        CancellableTask.__init__(self)
    async def run_task(self):
         await self.loop_check(interval_seconds=300)

class CancellableNotifier(NewStockNotifier, CancellableTask):
    def __init__(self):
        NewStockNotifier.__init__(self)
        CancellableTask.__init__(self)
    async def run_task(self):
        await self.notify_at_specified_times()

class CancellableCBMonitor(ConvertibleBondsMonitor, CancellableTask):
    def __init__(self):
        ConvertibleBondsMonitor.__init__(self)
        CancellableTask.__init__(self)
    async def run_task(self):
         await self.loop_check(interval_seconds=300)

async def main():
    notifier = CancellableNotifier()
    stock_monitor = CancellableStockMonitor(StockConfig())
    executor = QdiiStrategyExecutor()

    # Run the notifier task concurrently
    notification_task = asyncio.create_task(notifier.loop())

    # Start QDII Strategy Executor in a separate thread
    task1, task2, task3 = await executor.start()  # Updated to unpack three tasks

    # Stock monitoring (every 5 minutes)
    stock_monitoring_task = asyncio.create_task(stock_monitor.loop())

    # Convertible Bonds monitoring (every 5 minutes)
    cb_monitor = CancellableCBMonitor()
    cb_monitoring_task = asyncio.create_task(cb_monitor.loop())

    # US ETF premium daily report (14:40 after, once per trading day)
    us_etf_monitor = UsEtfPremiumMonitor()
    us_etf_task = asyncio.create_task(us_etf_monitor.loop())

    # Graceful shutdown on Ctrl+C
    async def shutdown_signal_handler(signum=None, frame=None):
        logging.info("Shutting down gracefully...")
        notifier.cancel()
        stock_monitor.cancel()
        executor.cancel()
        cb_monitor.cancel()
        us_etf_monitor.cancel()

        tasks = [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]
        logging.info(f"Cancelling {len(tasks)} running tasks...")
        
        for task in tasks:
            task.cancel()
        
        try:
            await asyncio.wait_for(
                asyncio.gather(*tasks, return_exceptions=True),
                timeout=5.0
            )
            logging.info("All tasks cancelled successfully")
        except asyncio.TimeoutError:
            logging.warning("Timeout while waiting for tasks to cancel")
        except Exception as e:
            logging.error(f"Error during shutdown: {e}", exc_info=True)

    # Register shutdown signal handler for graceful shutdown
    signal.signal(signal.SIGINT, lambda signum, frame: asyncio.create_task(shutdown_signal_handler(signum, frame)))
    signal.signal(signal.SIGTERM, lambda signum, frame: asyncio.create_task(shutdown_signal_handler(signum, frame)))

    try:
        while True:
            if date_utils.is_past_1500():
                logging.info("Time past 15:00, initiating shutdown...")
                await shutdown_signal_handler()
                break
            await asyncio.sleep(300)  # Check every 5 minutes
        await asyncio.gather(notification_task, task1, task2, task3,
                             stock_monitoring_task, cb_monitoring_task, us_etf_task)  # Added task3 + us_etf
    except asyncio.CancelledError:
        logging.info("Tasks were cancelled on shutdown")
    except Exception as e:
        logging.error(f"An unexpected error occurred: {e}", exc_info=True)

# Entry point
if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logging.info("Keyboard interrupt caught, exiting...")
    finally:
        logging.info("Exiting Application")