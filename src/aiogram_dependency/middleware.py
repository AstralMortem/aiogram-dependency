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
        resolved_deps = await self.resolver.resolve_dependencies(event, data)
        data.update(resolved_deps)
        return await handler(event, data)
