import asyncio
import time

class ConfigChangeHandler:
    def __init__(self, callback, loop, delay_sec=1.0):
        self.callback = callback  # async def callback()
        self.loop = loop
        self.delay_sec = delay_sec
        self.task = None  # 当前唯一的 debounce task
        self.start_time = None  # 首次变化时间

    def datachange_notification(self, node, val, data):
        async def delayed_apply():
            await asyncio.sleep(self.delay_sec)
            try:
                elapsed = time.time() - self.start_time
                #print(f"[INFO] Debounced apply triggered after {elapsed:.2f} seconds")
                await self.callback()
            except Exception as e:
                print(f"[ERROR] Callback failed: {e}")
            finally:
                self.task = None
                self.start_time = None

        def schedule():
            if self.start_time is None:
                self.start_time = time.time()

            if self.task:
                self.task.cancel()

            self.task = asyncio.create_task(delayed_apply())

        self.loop.call_soon_threadsafe(schedule)
