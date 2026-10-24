from contextlib import AsyncExitStack
import inspect
from typing import (
    Callable,
    Dict,
    Any,
    Set,
)
from .dependency import Dependency, Scope
from .registry import DependencyRegistry
from aiogram.types import TelegramObject
from aiogram_dependency.utils import (
    extract_handler_signature,
    extract_dependency,
    is_async_gen_callable,
    is_coroutine_callable,
    is_gen_callable,
    solve_generator,
    run_in_threadpool,
)


class DependencyResolver:
    def __init__(self, registry: DependencyRegistry):
        self.registry = registry

    async def resolve_dependencies(
        self,
        event: TelegramObject,
        data: Dict[str, Any],
        exit_stack: AsyncExitStack,
    ):
        signature = extract_handler_signature(data)
        # Request cache and cycle tracking are per call, so concurrent updates never share them
        request_cache: Dict[Callable, Any] = {}
        resolved_deps = {}
        for param_name, param in signature.parameters.items():
            dependency = extract_dependency(param)
            if dependency:
                # If dependency inside Dependency class empty just skip
                if dependency.dependency is None:
                    resolved_deps[param_name] = None
                    continue

                # Call main resolver
                resolved_value = await self._resolve_single_dep(
                    dependency,
                    event,
                    data,
                    resolved_deps,
                    exit_stack,
                    request_cache,
                    set(),
                )
                resolved_deps[param_name] = resolved_value

        data.update(resolved_deps)
        return data

    async def _resolve_single_dep(
        self,
        dependency: Dependency,
        event: TelegramObject,
        data: Dict[str, Any],
        resolved_deps: Dict[str, Any],
        exit_stack: AsyncExitStack,
        request_cache: Dict[Callable, Any],
        resolving: Set[Callable],
    ):
        dep_callable = dependency.dependency
        if dependency.scope == Scope.SINGLETON:
            cache, stack = self.registry.singleton_cache, self.registry.exit_stack
        elif dependency.scope == Scope.REQUEST:
            cache, stack = request_cache, exit_stack
        else:
            cache, stack = None, exit_stack

        if cache is not None and dep_callable in cache:
            return cache[dep_callable]

        if dep_callable in resolving:
            name = getattr(dep_callable, "__name__", repr(dep_callable))
            raise ValueError(f"Circular dependency detected: {name}")
        resolving.add(dep_callable)

        try:
            dependency_signature = inspect.signature(dep_callable)
            dependency_kwargs = {}
            for param_name, param in dependency_signature.parameters.items():
                # Set default values to handler
                if param_name in ["event", "message", "callback"]:
                    dependency_kwargs[param_name] = event
                elif param_name == "data":
                    dependency_kwargs[param_name] = data
                elif param_name in data:
                    dependency_kwargs[param_name] = data[param_name]
                elif param_name in resolved_deps:
                    dependency_kwargs[param_name] = resolved_deps[param_name]

                # Check if param is nested dependency and try resolve it
                nested_dependency = extract_dependency(param)
                if nested_dependency:
                    resolved_nested = await self._resolve_single_dep(
                        nested_dependency,
                        event,
                        data,
                        resolved_deps,
                        exit_stack,
                        request_cache,
                        resolving,
                    )
                    dependency_kwargs[param_name] = resolved_nested

            if is_gen_callable(dep_callable) or is_async_gen_callable(dep_callable):
                resolved_value = await solve_generator(
                    call=dep_callable, stack=stack, kwargs=dependency_kwargs
                )
            elif is_coroutine_callable(dep_callable):
                resolved_value = await dep_callable(**dependency_kwargs)
            else:
                resolved_value = await run_in_threadpool(dep_callable, **dependency_kwargs)

            if cache is not None:
                cache[dep_callable] = resolved_value
            return resolved_value
        finally:
            resolving.discard(dep_callable)
