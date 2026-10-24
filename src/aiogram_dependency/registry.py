from contextlib import AsyncExitStack
from typing import Any, Callable, Dict


class DependencyRegistry:
    def __init__(self):
        self.singleton_cache: Dict[Callable, Any] = {}
        # Singleton generators are closed on shutdown, not at the end of the request that created them
        self.exit_stack = AsyncExitStack()

    async def close(self):
        await self.exit_stack.aclose()
        self.singleton_cache.clear()
        self.exit_stack = AsyncExitStack()
