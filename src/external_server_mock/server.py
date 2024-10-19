#!/usr/bin/env python

import asyncio
import json
from asyncio import Task
from typing import Any

from websockets.asyncio.server import ServerConnection, serve


async def producer(websocket: ServerConnection) -> None:
    while True:
        await websocket.send(json.dumps({"type": "heartbeat"}))
        await asyncio.sleep(1)


expected_input: dict[str, Any] = {
    "type": "message",
    "id": 456,
    "payload": {
        "marketId": 123456,
        "selectionId": 987654,
        "odds": 2.2,
        "stake": 253.67,
        "currency": "USD",
        "date": "2021-05-18T21:32:42.324Z",
    },
}


async def message_producer(websocket: ServerConnection) -> None:
    while True:
        await websocket.send(json.dumps(expected_input))
        await asyncio.sleep(6)


async def consumer(websocket: ServerConnection) -> None:
    while True:
        message = await websocket.recv()
        print(message)


async def handler(websocket: ServerConnection) -> None:
    consumer_task: Task[None] = asyncio.create_task(consumer(websocket))
    producer_task: Task[None] = asyncio.create_task(producer(websocket))
    message_producer_task: Task[None] = asyncio.create_task(message_producer(websocket))
    await asyncio.wait(
        [consumer_task, producer_task, message_producer_task], return_when=asyncio.FIRST_COMPLETED
    )


async def run_server() -> None:
    async with serve(handler, "localhost", 8765):
        await asyncio.get_running_loop().create_future()


def main() -> None:
    asyncio.run(run_server())


if __name__ == "__main__":
    main()
