import asyncio
import json
import os
from datetime import UTC, datetime
from decimal import ROUND_DOWN, Decimal
from typing import Any

from aiohttp import ClientSession
from structlog import BoundLogger, get_logger
from websockets import Data, WebSocketClientProtocol, connect

logger: BoundLogger = get_logger(__package__)


class HearbeatTimeoutError(Exception):
    pass


class CurrencyConverter:
    def __init__(self) -> None:
        api_key: str | None = os.getenv("FREECURRENCY_API_KEY")
        assert api_key, "API_KEY environment variable is required"
        self.exchange_endpoint: str = f"https://api.freecurrencyapi.com/v1/latest?apikey={api_key}"

        self.currency_assignment_ws_uri: str = os.getenv(
            "CURRENCY_ASSIGNMENT_WS_URI", "ws://localhost:8765"
        )
        self.connection_retry_time: int = 5
        self.hearbeat_timeout: int = 2
        self.hearbeat_interval: int = 1

    async def async_run(self) -> None:
        logger.info("Starting app")
        try:
            await self.setup()
            await self.start()
        except asyncio.CancelledError:
            logger.info("App stopped")
        finally:
            await self.aclose()
            logger.info("App closed, resources released")

    def run(self) -> None:
        asyncio.run(self.async_run())

    async def setup(self) -> None:
        self.client_session: ClientSession = ClientSession()

    async def start(self) -> None:
        while True:
            logger.info("Creating new connection")
            try:
                async with connect(self.currency_assignment_ws_uri) as ws:
                    await self.handler(ws)
            except HearbeatTimeoutError:
                logger.warning(
                    f"Hearbeat timeout, reconnecting in {self.connection_retry_time} seconds"
                )
                await asyncio.sleep(self.connection_retry_time)
                logger.info("Reconnecting")
            except Exception as e:
                logger.error("Error in connection", error=e)
                logger.info(f"Reconnecting in {self.connection_retry_time} seconds")
                await asyncio.sleep(self.connection_retry_time)
                logger.info("Reconnecting")

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

    def format_stake(self, value: Decimal, precision: int) -> str:
        # Decimals are used to avoid floating point arithmetic errors
        return str(value.quantize(Decimal(f'1.{"0"*precision}'), rounding=ROUND_DOWN))

    async def convert_currency(self, msg: dict[str, Any]) -> dict[str, Any] | None:
        try:
            base_currency: str = msg["payload"]["currency"]
            base_stake: float = msg["payload"]["stake"]
            target_currency: str = "EUR"

            url: str = self.generate_get_exchange_rate_url(base_currency, target_currency)
            async with self.client_session.get(url) as response:
                data: dict[str, Any] = await response.json()
            rate: float = data["data"][target_currency]

            msg["payload"]["currency"] = target_currency
            new_stake: Decimal = Decimal(str(base_stake)) * Decimal(str(rate))
            msg["payload"]["stake"] = self.format_stake(new_stake, 5)
            msg["payload"]["date"] = datetime.now(UTC).isoformat().replace("+00:00", "Z")
            return msg
        except KeyError as error:
            logger.error("Missing key in message", error=error)
            if msg.get("id"):
                return self.generate_error_message(msg["id"], f"Missing key in message: {error}")
        except Exception as error:
            logger.error("Error converting currency", error=error)
            if msg.get("id"):
                return self.generate_error_message(msg["id"], str(error))
        return None

    async def consume(self, ws: WebSocketClientProtocol) -> None:
        logger.info("Starting consumer")
        last_heartbeat: datetime = datetime.now()
        while True:
            try:
                message: Data = await asyncio.wait_for(ws.recv(), timeout=self.hearbeat_timeout)
                data: dict[str, Any] = json.loads(message)
                if data.get("type") == "heartbeat":
                    if (datetime.now() - last_heartbeat).seconds > self.hearbeat_timeout:
                        raise HearbeatTimeoutError("Heartbeat timeout")
                    last_heartbeat = datetime.now()
                    continue
                if data.get("type") != "message":
                    logger.warning("Unknown message type", data=data)
                    continue

                await ws.send(json.dumps(await self.convert_currency(data)))
            except asyncio.TimeoutError:
                raise HearbeatTimeoutError("Heartbeat timeout")

    async def produce(self, ws: WebSocketClientProtocol) -> None:
        logger.info("Starting producer")
        while True:
            await ws.send(json.dumps({"type": "heartbeat"}))
            await asyncio.sleep(self.hearbeat_interval)

    async def handler(self, ws: WebSocketClientProtocol) -> None:
        consumer_task = asyncio.create_task(self.consume(ws))
        producer_task = asyncio.create_task(self.produce(ws))

        done, pending = await asyncio.wait(
            [consumer_task, producer_task],
            return_when=asyncio.FIRST_COMPLETED,
        )

        for task in pending:
            task.cancel()

        for task in done:
            if task.exception():
                raise task.exception()

        await ws.close()

    async def aclose(self) -> None:
        await self.client_session.close()
