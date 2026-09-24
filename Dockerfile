FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
        ffmpeg \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY pyproject.toml README.md ./
COPY videoseek ./videoseek
COPY config ./config
COPY scripts ./scripts

RUN pip install --no-cache-dir .

ENTRYPOINT ["cheatbench-cli"]
