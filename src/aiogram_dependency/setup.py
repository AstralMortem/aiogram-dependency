from aiogram import Dispatcher
from aiogram.dispatcher.event.telegram import TelegramEventObserver
from .middleware import DependencyMiddleware
from .registry import DependencyRegistry


def setup_dependency(
    dispatcher: Dispatcher,
    *,
    allowed_updates: list[str] | None = None,
    registry: DependencyRegistry | None = None,
):
    if not isinstance(dispatcher, Dispatcher):
        raise TypeError("dispatcher must be an instance of aiogram.Dispatcher")

    if allowed_updates is not None:
        for allowed_update in allowed_updates:
            if allowed_update not in dispatcher.observers:
                raise ValueError(f"`{allowed_update}` is not a valid allowed update")

    # Create dependency registry
    registry = registry or DependencyRegistry()

    for allowed_update in allowed_updates or dispatcher.resolve_used_update_types():
        observer: TelegramEventObserver = getattr(dispatcher, allowed_update)
        observer.middleware(DependencyMiddleware(registry))

    # Add shutdown hooks to properly close openend context in singletone cache
    async def on_shutdown():
        registry.reset_request_cache()
        registry.reset_singletone_cache()

    dispatcher.shutdown.register(on_shutdown)

    return registry
