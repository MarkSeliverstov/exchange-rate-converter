import asyncio
import json
import os
from typing import Any

from aiohttp import ClientSession
from structlog import BoundLogger, get_logger
from websockets import Data, WebSocketClientProtocol, connect

logger: BoundLogger = get_logger(__package__)


class App:
    def __init__(self) -> None:
        self.client_session: ClientSession = ClientSession()
        api_key: str | None = os.getenv("FREECURRENCY_API_KEY")
        assert api_key, "API_KEY environment variable is required"
        self.exchange_endpoint: str = f"https://freecurrencyapi.com/api/v1/latest?apikey={api_key}"

        self.ws_uri: str = "wss://currency-assignment.ematiq.com"
        self.connection_retry_time: int = 5
        self.hearbeat_timeout: int = 2
        self.hearbeat_interval: int = 1

    async def async_run(self) -> None:
        logger.info("Starting app")
        try:
            await self.start()
        except asyncio.CancelledError:
            logger.info("App stopped")
        finally:
            await self.aclose()
            logger.info("App closed, resources released")

    def run(self) -> None:
        asyncio.run(self.async_run())

    async def start(self) -> None:
        while True:
            logger.info("Creating new connection")
            try:
                async with connect(self.ws_uri) as ws:
                    await self.handler(ws)
            except Exception as e:
                logger.error("Error in connection", error=e)
                logger.info(f"Reconnecting in {self.connection_retry_time} seconds")
                await asyncio.sleep(self.connection_retry_time)

    def generate_get_exchange_rate_url(self, base_currency: str, target_currency: str) -> str:
        return (
            f"{self.exchange_endpoint}&currencies={target_currency}&base_currency={base_currency}"
        )

    def generate_error_message(self, id: int, error: Exception) -> dict[str, Any]:
        return {
            "type": "error",
            "id": id,
            "message": f"Unable to convert stake. Error: {str(error)}",
        }

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
            msg["payload"]["stake"] = base_stake * rate
            return msg
        except Exception as error:
            logger.error("Error converting currency", error=str(error))
            if msg.get("id"):
                return self.generate_error_message(msg["id"], error)

    async def consume(self, ws: WebSocketClientProtocol) -> None:
        logger.info("Starting consumer")
        while True:
            try:
                message: Data = await asyncio.wait_for(ws.recv(), timeout=self.hearbeat_timeout)
                data: dict[str, Any] = json.loads(message)
                if data.get("type") == "heartbeat" or data.get("type") == "message":
                    # Ignore heartbeat and unknown message types
                    continue
                logger.info("Received message", data=data)
                await ws.send(json.dumps(await self.convert_currency(data)))
            except asyncio.TimeoutError:
                logger.warning("Heartbeat timeout, trying to reconnect")
                break

    async def produce(self, ws: WebSocketClientProtocol) -> None:
        logger.info("Starting producer")
        while True:
            await ws.send(json.dumps({"type": "heartbeat"}))
            await asyncio.sleep(self.hearbeat_interval)

    async def handler(self, ws: WebSocketClientProtocol) -> None:
        consumer_task = asyncio.create_task(self.consume(ws))
        producer_task = asyncio.create_task(self.produce(ws))
        _, pending = await asyncio.wait(
            [consumer_task, producer_task],
            return_when=asyncio.FIRST_COMPLETED,
        )
        for task in pending:
            task.cancel()

    async def aclose(self) -> None:
        await self.client_session.close()
