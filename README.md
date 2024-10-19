# Exchange Rate Converter

Real-time exchange rate conversion service working over a websocket connection.\
CCA time spent on the project: 5h

## Requirementsa

- API key from [app.freecurrencyapi.com](https://app.freecurrencyapi.com)
- Server to connect to.

## Usage

First, you need to set the environment variables:

```bash
export FREECURRENCY_API_KEY=<your_api_key>  # API key from "https://app.freecurrencyapi.com"
export CURRENCY_ASSIGNMENT_WS_URI=<ws_uri>  # URI of the WebSocket server to connect to
                                            # (optional, default is ws://localhost:8765)
```

After setting the environment variables, you can run the application using

```bash
docker-compose up
```

or

```bash
poetry install
poetry run rate_converter
```

## Architectural and technical decisions

1. **WebSocket Communication**:
   - Using WebSockets for real-time communication, enabling low-latency data
     exchange.
   - A heartbeat mechanism is implemented by 2 independent tasks to ensure
     communication health:
        - `produce` task sends heartbeat messages to the server every time
          interval.
        - `consume` task listens for heartbeat messages from the server and if
          no message is received for more than interval, it cancels the tasks
          and refreshes the connection.

2. **Caching Mechanism**:
    - Exchange rates are cached for 2 hours using `TTLCache` - light and simple
      cache implementation.

3. **Error Handling**:
    - Custom exceptions (`HearbeatTimeoutError` and `InvalidCurrencyError`) are
      implemented to provide clear error messages

4. **Decimal Arithmetic**:
    - `Decimal` are used to avoid arithmetic errors with floating-point
      numbers.

5. **Secrets Management (actually for WS server URL and API key)**:
    - Secrets are stored in a `.env` file and loaded in runtime

6. **aiohttp ClientSession**:
    - `ClientSession` is used to make HTTP requests to the external API for
      exchange rates. It creates one instance on `setup` and closes it on
      `aclose`. So, it reuses the same connection for multiple requests.

7. **Application itself**:
    - `CurrencyConverter` has 2 entrypoints (async and sync)

8. **Logging**:
    - Using `structlog` for better logging.

9. **Containerization**:
    - `Dockerfile` and `docker-compose.yml` are provided to run the application
      in a container.

- NOTE:
  - `datetime.now(UTC).isoformat().replace("+00:00", "Z")` replaces the
      timezone offset with 'Z' to make it expected by the external API (defined
      in the TASK.md). In practice, I would use
      `datetime.now(UTC).isoformat()`.

## Development

<details>

```bash
poetry install
```

## Usage

```bash
poetry run rate_converter
```

## Testing

```bash
pytest -c pyproject.toml
```

## Formatting

```bash
poetry run poe format-code
```

</details>
