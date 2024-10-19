# Exchange Rate Conversion Service

## Introduction

The trading department has discovered new platform where the trading takes
place in various exchange currencies. Since the platform offering looks
promising, the decision is to integrate it into our trading platform.

Fortunately, most of the trading pipeline is already implemented and in order
to integrate the platform end to end, there is one missing piece - service
providing real time exchange rate conversion.

## Requirements

The service is expected to handle requests over websocket connection. The
service is expected to convert from various exchange rates into EUR.

- the trading pipeline service `currency-assignment` generating the requests is
  running at `wss://some-uri.com`
- the communication health is ensured by sending periodic bi-directional
  heartbeat messages. In particular, both `currency-assignment` and the
  currency conversion service are sending heartbeat message each second over
  the websocket connection
- in case the heartbeat is not received for more than 2 seconds, it is
  necessary to refresh the websocket connection
- `currency-assignment` is sending requests for conversion in random intervals
- response to the conversion requests must contain update field `stake`
  according to the exchange rate valid at `date` specified in the message.
  Stake precision should be up to 5 decimal places
- in case conversion fails, the service is expected to reply with error message
  describing what went wrong (e.g. requested exchange rate conversion is not
  supported)
- external exchange rates are expected to be cached for 2 hours to prevent
  unnecessary traffic on external API

In order to obtain valid exchange rates, feel free to use any of external API
like <https://freecurrencyapi.com/>, <https://exchangerate.host> or other.

## Message types

Following section provides example of message formats:

### Heartbeat message

```json
{
    "type": "heartbeat"
}
```

### Currency conversion request message

```json
{
    "type": "message",
    "id": 456,
    "payload": {
        "marketId": 123456,
        "selectionId": 987654,
        "odds": 2.2,
        "stake": 253.67,
        "currency": "USD",
        "date": "2021-05-18T21:32:42.324Z"
    }
}
```

### Currency conversion success response message

```json
{
    "type": "message",
    "id": 456,
    "payload": {
        "marketId": 123456,
        "selectionId": 987654,
        "odds": 2.2,
        "stake": 207.52054,
        "currency": "EUR",
        "date": "2021-05-18T21:32:42.412Z"
    }
}

```

### Currency conversion error response message

```json
{
    "type": "error",
    "id": 456,
    "message": "Unable to convert stake. Error: @@@"
}
```

Replace `@@@` with the text of the error which occurred.

## Goal

Implement the service in Python using
[asyncio](https://docs.python.org/3/library/asyncio.html). Feel free to use any
additional libraries and frameworks you find suitable. The service is expected
to be in production grade quality and/or the shortcuts made should be properly
documented.

Along the service code itself, the solution should contain `README.md`
documenting how to run the service locally together with the description of any
important architectural and technical decisions you made.
