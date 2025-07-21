from typing import Callable, Optional
from enum import StrEnum


class Scope(StrEnum):
    SINGLETON = "singleton"
    REQUEST = "request"
    TRANSIENT = "transient"


class Dependency:
    def __init__(
        self, dependency: Optional[Callable] = None, scope: Scope = Scope.REQUEST
    ):
        self.dependency = dependency
        self.scope = scope

    def __repr__(self):
        attr = getattr(self.dependency, "__name__", type(self.dependency).__name__)
        return f"Depends({attr})"


def Depends(
    dependency: Optional[Callable] = None, *, scope: Scope = Scope.REQUEST
) -> Dependency:
    return Dependency(dependency, scope=scope)
