from contextlib import AsyncExitStack, asynccontextmanager, contextmanager
import inspect
from typing import (
    Annotated,
    Callable,
    Dict,
    Any,
    get_args,
    get_origin,
    ContextManager,
    AsyncContextManager,
)
from .dependency import Dependency, Scope
from .registry import DependencyRegistry
from .concurency import contextmanager_in_threadpool, run_in_threadpool
from aiogram.types import TelegramObject


class DependencyResolver:
    def __init__(self, registry: DependencyRegistry):
        self.registry = registry
        self._resolving: set = set()

        self.active_contexts = {}  # Track active context managers
        self.cleanup_tasks = []  # Track cleanup tasks

    async def resolve_dependencies(
        self,
        event: TelegramObject,
        data: Dict[str, Any],
        async_exit_stack: AsyncExitStack,
    ):
        # Callable stored in HandlerObject dataclass, which in `data` dict;
        # Try to get callable
        call = data.get("handler", None)
        if call and hasattr(call, "callback"):
            func = getattr(call, "callback")
            sig = inspect.signature(func)
            cache_key = self.registry.get_cache_key(event, data)
            resolved_deps = {}

            for param_name, param in sig.parameters.items():
                if self._is_dependency_param(param):
                    dep, scope = self._get_dependency_from_param(param)
                    # If dependency inside Dependency class empty just skip
                    if dep is None:
                        resolved_deps[param_name] = None
                        continue

                    # Check if circular dependency
                    if dep in self._resolving:
                        raise ValueError(
                            f"Circular dependency detected: {dep.__name__}"
                        )
                    # Call main resolver
                    resolved_value = await self._resolve_single_dependency(
                        dep,
                        scope,
                        event,
                        data,
                        cache_key,
                        resolved_deps,
                        async_exit_stack,
                    )
                    resolved_deps[param_name] = resolved_value
            return resolved_deps
        return {}

    async def _resolve_single_dependency(
        self,
        dep: Callable,
        scope: Scope,
        event: TelegramObject,
        data: Dict[str, Any],
        cache_key: str,
        resolved_deps: Dict[str, Any],
        async_exit_stack: AsyncExitStack,
    ):
        # Check if dependency in cache, return if True
        cached_value = self.registry.get_dependency(dep, scope, cache_key)
        if cached_value is not None:
            return cached_value

        # Add resolving lock
        self._resolving.add(dep)

        try:
            dep_sig = inspect.signature(dep)
            dep_kwargs = {}
            nested_dependencies = set()

            for param_name, param in dep_sig.parameters.items():
                # set default aiogram kwargs, message, event, etc..
                if param_name == "event":
                    dep_kwargs[param_name] = event
                elif param_name == "data":
                    dep_kwargs[param_name] = data
                elif param_name in data:
                    dep_kwargs[param_name] = data[param_name]
                elif param_name in resolved_deps:
                    dep_kwargs[param_name] = resolved_deps[param_name]

                # check if dependency
                elif self._is_dependency_param(param):
                    # Recursivly resolve dependencies
                    nested_dep, nested_scope = self._get_dependency_from_param(param)
                    nested_dependencies.add(nested_dep)
                    nested_value = await self._resolve_single_dependency(
                        nested_dep,
                        nested_scope,
                        event,
                        data,
                        cache_key,
                        resolved_deps,
                        async_exit_stack,
                    )
                    dep_kwargs[param_name] = nested_value

            # Resolve differend dependency types
            if self._is_gen_callable(dep) or self._is_async_gen_callable(dep):
                resolved_value = await self._solve_generator(
                    call=dep, stack=async_exit_stack, kwargs=dep_kwargs
                )
            elif self._is_coroutine_callable(dep):
                resolved_value = await dep(**dep_kwargs)
            else:
                resolved_value = await run_in_threadpool(dep, **dep_kwargs)
            # update registry cache
            self.registry.set_dependency(dep, resolved_value, scope, cache_key)
            return resolved_value

        finally:
            # Remove resolving lock
            self._resolving.discard(dep)

    def _get_dependency_from_param(self, param: inspect.Parameter) -> Dependency:
        # Extract Dependency class from Annotated or param.default
        if get_origin(param.annotation) is Annotated:
            for meta in get_args(param.annotation)[1:]:
                if isinstance(meta, Dependency):
                    return (meta.dependency, meta.scope)
        elif isinstance(param.default, Dependency):
            return (param.default.dependency, param.default.scope)

        return False, None

    def _is_dependency_param(self, param: inspect.Parameter) -> bool:
        # Check if param is Annotated[..., Depends()] or direct Depends()
        if get_origin(param.annotation) is Annotated:
            for meta in get_args(param.annotation)[1:]:
                if isinstance(meta, Dependency):
                    return True
        elif isinstance(param.default, Dependency):
            return True
        return False

    def _is_gen_callable(self, call: Callable[..., Any]) -> bool:
        if inspect.isgeneratorfunction(call):
            return True
        dunder_call = getattr(call, "__call__", None)  # noqa: B004
        return inspect.isgeneratorfunction(dunder_call)

    def _is_async_gen_callable(self, call: Callable[..., Any]) -> bool:
        if inspect.isasyncgenfunction(call):
            return True
        dunder_call = getattr(call, "__call__", None)  # noqa: B004
        return inspect.isasyncgenfunction(dunder_call)

    def _is_coroutine_callable(self, call: Callable[..., Any]) -> bool:
        if inspect.isroutine(call):
            return inspect.iscoroutinefunction(call)
        if inspect.isclass(call):
            return False
        dunder_call = getattr(call, "__call__", None)  # noqa: B004
        return inspect.iscoroutinefunction(dunder_call)

    async def _solve_generator(
        self, *, call: Callable[..., Any], stack: AsyncExitStack, kwargs: Dict[str, Any]
    ) -> Any:
        if self._is_gen_callable(call):
            cm = contextmanager_in_threadpool(contextmanager(call)(**kwargs))
        elif self._is_async_gen_callable(call):
            cm = asynccontextmanager(call)(**kwargs)
        return await stack.enter_async_context(cm)
