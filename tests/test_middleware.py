from unittest.mock import AsyncMock
import pytest
from aiogram.types import Message
from aiogram_dependency.dependency import Depends


@pytest.mark.asyncio
async def test_middleware_injects_dependencies(middleware, mock_message, mock_data):
    def get_test_service():
        return "injected_service"

    # Create handler mock
    handler = AsyncMock()

    async def test_handler(event: Message, service: str = Depends(get_test_service)):
        await handler(event, service)
        return "handler_result"

    # Inject callable to data handler.
    setattr(mock_data["handler"], "callback", test_handler)

    result = await middleware(test_handler, mock_message, mock_data)

    # Check that dependency was injected into data
    assert "service" in mock_data
    assert mock_data["service"] == "injected_service"
    assert result == "handler_result"


@pytest.mark.asyncio
async def test_middleware_handles_handler_exception(
    middleware, mock_message, mock_data
):
    def get_test_service():
        return "service"

    async def failing_handler(event: Message, service: str = Depends(get_test_service)):
        raise ValueError("Handler failed")

    # Inject callable to data handler.
    setattr(mock_data["handler"], "callback", failing_handler)

    with pytest.raises(ValueError, match="Handler failed"):
        await middleware(failing_handler, mock_message, mock_data)

    # Dependency should still be injected
    assert mock_data["service"] == "service"


@pytest.mark.asyncio
async def test_middleware_skips_non_dependency_params(
    middleware, mock_message, mock_data
):
    async def test_handler(
        event: Message, normal_param: str = "default_value", data: dict = None
    ):
        return "result"

    # Inject callable to data handler.
    setattr(mock_data["handler"], "callback", test_handler)

    original_data = mock_data.copy()
    result = await middleware(test_handler, mock_message, mock_data)

    # No dependencies should be added
    assert mock_data == original_data
    assert result == "result"
