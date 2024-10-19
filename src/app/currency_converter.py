import asyncio
import json
import os
from datetime import UTC, datetime
from decimal import ROUND_DOWN, Decimal
from typing import Any

from aiohttp import ClientSession, TCPConnector
from cachetools import TTLCache
from structlog import BoundLogger, get_logger
from websockets import ConnectionClosedOK, Data, WebSocketClientProtocol, connect

logger: BoundLogger = get_logger(__package__)


class HearbeatTimeoutError(TimeoutError):
    pass


class InvalidCurrencyError(ValueError):
    def __init__(self, base_currency: str, target_currency: str) -> None:
        message: str = f"Invalid currency pair: {base_currency}->{target_currency}"
        super().__init__(message)


cache: TTLCache[str, Decimal | None] = TTLCache(maxsize=100, ttl=2 * 60 * 60)
"""
Cache to store exchange rates for 2 hours, as external exchange rates are
expected to be cached for 2 hours to prevent unnecessary traffic on external API.
"""


class CurrencyConverter:
    client_session: ClientSession | None = None

    def __init__(self) -> None:
        api_key: str | None = os.getenv("FREECURRENCY_API_KEY")
        assert api_key, "API_KEY environment variable is required"
        uri: str | None = os.getenv("CURRENCY_ASSIGNMENT_WS_URI")
        assert uri, "CURRENCY_ASSIGNMENT_WS_URI environment variable is required"
        self.exchange_endpoint: str = f"https://api.freecurrencyapi.com/v1/latest?apikey={api_key}"
        self.currency_assignment_ws_uri: str = uri
        self.connection_retry_time: int = 5
        self.hearbeat_timeout: int = 2
        self.hearbeat_interval: int = 1

    def run(self) -> None:
        asyncio.run(self.async_run())

    async def async_run(self) -> None:
        logger.info("Starting app")
        try:
            await self.setup()
            await self.start()
        except (Exception, asyncio.CancelledError):
            logger.info("App stopped")
        finally:
            await self.aclose()
            logger.info("App closed, resources released")

    async def setup(self) -> None:
        self.client_session = ClientSession(
            connector=TCPConnector(verify_ssl=os.getenv("VERIFY_SSL") == "True")
        )

    async def start(self) -> None:
        while True:
            logger.info("Creating new connection")
            try:
                async with connect(self.currency_assignment_ws_uri) as ws:
                    await self.handler(ws)
            except (HearbeatTimeoutError, OSError) as error:
                logger.warning(
                    f"Reconnecting in {self.connection_retry_time} seconds due error: {error}"
                )
                await asyncio.sleep(self.connection_retry_time)
            except Exception as error:
                logger.error("Unexpected error", error=error)
                raise error

    def generate_get_exchange_rate_url(self, base_currency: str, target_currency: str) -> str:
        return (
            f"{self.exchange_endpoint}&currencies={target_currency}&base_currency={base_currency}"
        )

    def generate_error_message(self, id: int, error: str) -> dict[str, Any]:
        return {
            "type": "error",
            "id": id,
            "message": f"Unable to convert stake. Error: {error}",
        }

    def generate_response_message(
        self, original_message: dict[str, Any], new_stake: float, new_currency: str
    ) -> dict[str, Any]:
        return {
            "type": "message",
            "id": original_message["id"],
            "payload": {
                "marketId": original_message["payload"]["marketId"],
                "selectionId": original_message["payload"]["selectionId"],
                "odds": original_message["payload"]["odds"],
                "stake": new_stake,
                "currency": new_currency,
                "date": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
            },
        }

    def format_stake(self, value: Decimal, precision: int) -> float:
        # Decimals are used to avoid floating point arithmetic errors
        return float(value.quantize(Decimal(f'1.{"0"*precision}'), rounding=ROUND_DOWN))

    async def get_exchange_rate(self, base_currency: str, target_currency: str) -> Decimal:
        assert self.client_session

        cache_key: str = f"{base_currency}-{target_currency}"
        rate: Decimal | None
        if cache_key in cache:
            rate = cache[cache_key]
            logger.debug("Using cached rate", rate=str(rate), pair=cache_key)
            if not rate:
                raise InvalidCurrencyError(base_currency, target_currency)
            return rate

        url: str = self.generate_get_exchange_rate_url(base_currency, target_currency)
        async with self.client_session.get(url) as response:
            data: dict[str, Any] = await response.json()

        if data.get("errors"):
            cache[cache_key] = None
            logger.warning("Invalid request to API", pair=cache_key, errors=data["errors"])
            raise InvalidCurrencyError(base_currency, target_currency)

        rate = Decimal(str(data["data"][target_currency]))
        cache[cache_key] = rate
        logger.debug("Received rate from API", pair=cache_key, rate=str(rate))
        return rate

    async def convert_currency(self, msg: dict[str, Any]) -> dict[str, Any]:
        try:
            base_currency: str = msg["payload"]["currency"]
            base_stake: float = msg["payload"]["stake"]
            target_currency: str = "EUR"

            rate: Decimal = await self.get_exchange_rate(base_currency, target_currency)
            new_stake: Decimal = Decimal(str(base_stake)) * rate
            return self.generate_response_message(
                msg, self.format_stake(new_stake, 5), target_currency
            )
        except KeyError as error:
            logger.error("Missing key in message", error=error)
            return self.generate_error_message(msg["id"], f"Missing key in message: {error}")
        except InvalidCurrencyError as error:
            return self.generate_error_message(msg["id"], str(error))
        except Exception as error:
            logger.error("Unexpected error", error=error)
            return self.generate_error_message(msg["id"], str(error))

    async def consume(self, ws: WebSocketClientProtocol) -> None:
        logger.info("Starting consumer")
        last_heartbeat: datetime = datetime.now()
        while True:
            try:
                message: Data = await asyncio.wait_for(ws.recv(), timeout=self.hearbeat_timeout)
                data: dict[str, Any] = json.loads(message)

                if data.get("type") == "heartbeat":
                    logger.debug("Received heartbeat, server is alive :D")
                    if (datetime.now() - last_heartbeat).seconds > self.hearbeat_timeout:
                        raise HearbeatTimeoutError()
                    last_heartbeat = datetime.now()
                    continue

                if data.get("type") != "message":
                    logger.debug("Unknown message type", data=data)
                    continue

                logger.info("Received message", data=data)
                response: dict[str, Any] | None = await self.convert_currency(data)
                logger.info("Sending response", data=response)
                await ws.send(json.dumps(response))
            except asyncio.TimeoutError:
                raise HearbeatTimeoutError()
            except ConnectionClosedOK:
                return

    async def produce(self, ws: WebSocketClientProtocol) -> None:
        logger.info("Starting producer")
        while True:
            await ws.send(json.dumps({"type": "heartbeat"}))
            await asyncio.sleep(self.hearbeat_interval)

    async def handler(self, ws: WebSocketClientProtocol) -> None:
        consumer_task: asyncio.Task[None] = asyncio.create_task(self.consume(ws))
        producer_task: asyncio.Task[None] = asyncio.create_task(self.produce(ws))

        done, pending = await asyncio.wait(
            [consumer_task, producer_task],
            return_when=asyncio.FIRST_COMPLETED,
        )

        for task in pending:
            # Cancel remaining tasks if one of them is done as we want to close and reconnect
            task.cancel()

        for task in done:
            if task.exception() is not None:
                raise task.exception()  # type: ignore[misc]

    async def aclose(self) -> None:
        if self.client_session:
            await self.client_session.close()
