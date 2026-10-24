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

    # Default to every event observer so routers included after setup are covered too
    default_updates = [name for name in dispatcher.observers if name not in ("update", "error")]
    for allowed_update in allowed_updates or default_updates:
        observer: TelegramEventObserver = getattr(dispatcher, allowed_update)
        observer.middleware(DependencyMiddleware(registry))

    # Close singleton generators (engines, pools) on shutdown
    dispatcher.shutdown.register(registry.close)

    return registry
