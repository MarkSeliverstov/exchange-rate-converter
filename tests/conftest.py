from collections.abc import AsyncIterator
from unittest.mock import AsyncMock, patch

from pytest import fixture

from app.currency_converter import CurrencyConverter


@fixture
async def app() -> AsyncIterator[CurrencyConverter]:
    with patch("app.currency_converter.os.getenv", return_value="test"):
        app: CurrencyConverter = CurrencyConverter()
    app.client_session = AsyncMock()
    yield app
    await app.aclose()
