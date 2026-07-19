FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# supercronic: container-friendly cron (runs as PID 1, logs to stdout)
ARG TARGETARCH
ADD https://github.com/aptible/supercronic/releases/download/v0.2.33/supercronic-linux-${TARGETARCH} /usr/local/bin/supercronic
RUN chmod +x /usr/local/bin/supercronic

WORKDIR /app

# dependency layer first: rebuilt only when the lockfile changes
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-install-project --no-dev

COPY . .
RUN uv sync --frozen --no-dev

CMD ["supercronic", "/app/crontab"]
