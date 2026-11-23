
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONNOUSERSITE=1

WORKDIR /app

# Install the Allos MCP Python package.
COPY pyproject.toml README.md ./
COPY src ./src

RUN pip install --no-cache-dir . \
    && useradd \
        --uid 10001 \
        --create-home \
        --shell /usr/sbin/nologin \
        allos

# Run without root privileges.
USER allos

# Streamable HTTP over TLS.
EXPOSE 8765

ENTRYPOINT ["allos-mcp"]

# The image defaults to STDIO. HTTP requires explicit
# TLS credentials, a Bearer token and startup arguments.
CMD ["--transport", "stdio"]
