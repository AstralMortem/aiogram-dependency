from contextlib import AsyncExitStack
from aiogram.dispatcher.middlewares.base import BaseMiddleware
from typing import Callable, Dict, Any, Awaitable, Optional
from aiogram.types import TelegramObject
from .registry import DependencyRegistry
from .resolver import DependencyResolver


class DependencyMiddleware(BaseMiddleware):
    def __init__(self, registry: Optional[DependencyRegistry] = None):
        self.registry = registry or DependencyRegistry()
        self.resolver = DependencyResolver(self.registry)

    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any],
    ):
        # Resolve dependencies and update data dict
        async with AsyncExitStack() as async_exit_stac:
            resolved_deps = await self.resolver.resolve_dependencies(
                event, data, async_exit_stac
            )
            data.update(resolved_deps)
            return await handler(event, data)
