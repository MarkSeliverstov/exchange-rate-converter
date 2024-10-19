from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest

from app.currency_converter import CurrencyConverter


def test_format_stake(app: CurrencyConverter) -> None:
    assert app.format_stake(Decimal("253.67"), 5) == "253.67000"
    assert app.format_stake(Decimal("253.67"), 2) == "253.67"
    assert app.format_stake(Decimal("253.67"), 0) == "253"


@pytest.mark.asyncio
async def test_get_exchange_rate(app: CurrencyConverter) -> None:
    target_currency = "EUR"
    assert app.client_session
    app.client_session.get = MagicMock()  # type: ignore[method-assign]
    app.client_session.get.return_value.__aenter__.return_value.status = 200
    app.client_session.get.return_value.__aenter__.return_value.json.return_value = {
        "data": {target_currency: 0.825}
    }

    cache: dict[str, Decimal]
    with patch("app.currency_converter.cache", {}) as cache:
        rate: Decimal = await app.get_exchange_rate("USD", target_currency)
        assert rate == Decimal("0.825")
        assert cache == {f"USD-{target_currency}": Decimal("0.825")}


@pytest.mark.asyncio
async def test_get_exchange_rate_with_cache(app: CurrencyConverter) -> None:
    target_currency = "EUR"
    with patch("app.currency_converter.cache", {f"USD-{target_currency}": Decimal("0.825")}):
        rate: Decimal = await app.get_exchange_rate("USD", target_currency)
        assert rate == Decimal("0.825")
