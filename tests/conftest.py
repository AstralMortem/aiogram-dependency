from unittest.mock import Mock
from aiogram_dependency.registry import DependencyRegistry
from aiogram_dependency.resolver import DependencyResolver
from aiogram_dependency.middleware import DependencyMiddleware
from aiogram.types import User, Chat, Message
import pytest


@pytest.fixture
def registry():
    return DependencyRegistry()


@pytest.fixture
def resolver(registry):
    return DependencyResolver(registry)


@pytest.fixture
def middleware(registry):
    return DependencyMiddleware(registry)


@pytest.fixture
def mock_message():
    """Create a mock Message object"""
    user = Mock(spec=User)
    user.id = 123
    user.first_name = "John"

    chat = Mock(spec=Chat)
    chat.id = 456
    chat.type = "private"

    message = Mock(spec=Message)
    message.from_user = user
    message.chat = chat
    message.text = "test message"

    return message


@pytest.fixture
def mock_data():
    """Create mock handler data"""
    return {"bot": Mock(), "event_context": {}, "handler": Mock()}
