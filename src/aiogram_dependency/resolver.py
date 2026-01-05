from contextlib import AsyncExitStack
import inspect
from typing import (
    Dict,
    Any,
)
from .dependency import Dependency
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
        self._resolving: set = set()

    async def resolve_dependencies(
        self,
        event: TelegramObject,
        data: Dict[str, Any],
        exit_stack: AsyncExitStack,
    ):
        signature = extract_handler_signature(data)
        cache_key = self.registry.get_cache_key(event)
        resolved_deps = {}
        for param_name, param in signature.parameters.items():
            dependency = extract_dependency(param)
            if dependency:
                # If dependency inside Dependency class empty just skip
                if dependency.dependency is None:
                    resolved_deps[param_name] = None
                    continue

                if dependency.dependency in self._resolving:
                    raise ValueError(
                        f"Circular dependency detected: {dependency.dependency.__name__}"
                    )
                # Call main resolver
                resolved_value = await self._resolve_single_dep(
                    dependency,
                    event,
                    data,
                    cache_key,
                    resolved_deps,
                    exit_stack,
                )
                resolved_deps[param_name] = resolved_value

        data.update(resolved_deps)
        return data

    async def _resolve_single_dep(
        self,
        dependency: Dependency,
        event: TelegramObject,
        data: Dict[str, Any],
        cache_key: str,
        resolved_deps: Dict[str, Any],
        exit_stack: AsyncExitStack,
    ):
        cached_value = self.registry.get_dependency(dependency, cache_key)
        if cached_value is not None:
            return cached_value

        dep_callable = dependency.dependency
        self._resolving.add(dep_callable)

        try:
            dependency_signature = inspect.signature(dep_callable)
            dependency_kwargs = {}
            nested_dependencies = set()
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
                    nested_dependencies.add(nested_dependency.dependency)
                    resolved_nested = await self._resolve_single_dep(
                        nested_dependency, event, data, cache_key, resolved_deps, exit_stack
                    )
                    dependency_kwargs[param_name] = resolved_nested

            if is_gen_callable(dep_callable) or is_async_gen_callable(dep_callable):
                resolved_value = await solve_generator(
                    call=dep_callable, stack=exit_stack, kwargs=dependency_kwargs
                )
            elif is_coroutine_callable(dep_callable):
                resolved_value = await dep_callable(**dependency_kwargs)
            else:
                resolved_value = await run_in_threadpool(dep_callable, **dependency_kwargs)

            self.registry.set_dependency(dependency, resolved_value, cache_key)
            return resolved_value
        finally:
            self._resolving.discard(dep_callable)
