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
        async with AsyncExitStack() as exit_stack:
            data = await self.resolver.resolve_dependencies(event, data.copy(), exit_stack)
            # Reset request registry cache after each request to enshure that some connections return to pool (for example sqlalchemy session)
            self.registry.reset_request_cache()
            return await handler(event, data)
