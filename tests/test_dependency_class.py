from aiogram_dependency.dependency import Dependency, Depends, Scope


def test_depends_func():
    def dummy_func():
        pass

    dep = Depends(dummy_func, scope=Scope.SINGLETON)

    assert isinstance(dep, Dependency)
    assert dep.dependency == dummy_func
    assert dep.scope == Scope.SINGLETON


def test_depends_default_scope():
    dep = Depends(lambda x: True)
    assert dep.scope == Scope.REQUEST
