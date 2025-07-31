import asyncio

class ConfigChangeHandler:
    def __init__(self, callback, loop):
        self.callback = callback  # 应该是一个 async 函数
        self.loop = loop

    def datachange_notification(self, node, val, data):
        try:

            coro = self.callback()  # 👈 必须返回 coroutine 对象
            if asyncio.iscoroutine(coro):
                self.loop.call_soon_threadsafe(asyncio.create_task, coro)
            else:
                print(f"[WARN] callback is not coroutine, got: {type(coro)}")

        except Exception as e:
            print(f"[EXCEPTION in datachange_notification] {e}")
