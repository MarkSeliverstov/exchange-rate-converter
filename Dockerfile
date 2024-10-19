FROM python:3.11-slim

LABEL maintainer="seliverstovmd@gmail.com"
WORKDIR /app
COPY . .
RUN python -m pip install poetry==1.8.3
RUN poetry install --only main
ENTRYPOINT ["poetry", "run", "rate_converter"]
