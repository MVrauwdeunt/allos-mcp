
"""Read-only Allos MCP server with authenticated HTTPS transport."""

import argparse
import hmac
import os
import sqlite3
import ssl

from functools import lru_cache
from pathlib import Path

import uvicorn
from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings
from starlette.types import ASGIApp, Receive, Scope, Send

from . import __version__
from .db import AllosDB


# Explicit host allowlist for DNS rebinding protection.
allowed_hosts = [
    "localhost:*",
    "127.0.0.1:*",
    "[::1]:*",
]

allowed_hosts.extend(
    host.strip()
    for host in os.environ.get(
        "ALLOS_MCP_ALLOWED_HOSTS", ""
    ).split(",")
    if host.strip()
)

mcp = FastMCP(
    "allos-mcp",
    json_response=True,
    host="127.0.0.1",
    port=8765,
    transport_security=TransportSecuritySettings(
        enable_dns_rebinding_protection=True,
        allowed_hosts=allowed_hosts,
        allowed_origins=[],
    ),
)

# Report the actual installed package version to MCP clients.
mcp._mcp_server.version = __version__


@lru_cache(maxsize=1)
def database() -> AllosDB:
    """Return the profile-scoped, read-only Allos database."""
    return AllosDB(
        os.environ.get("ALLOS_DB_PATH", "/data/allos.db"),
        int(os.environ["ALLOS_PROFILE_ID"]),
    )


@mcp.tool()
def allos_catalog() -> list[dict]:
    """List reviewed Allos health tables and their readable columns."""
    return database().catalog()


@mcp.tool()
def allos_metrics() -> list[dict]:
    """List available metric names and counts for the configured profile."""
    return database().metrics()


@mcp.tool()
def allos_read(
    table: str,
    fields: list[str] | None = None,
    start: str | None = None,
    end: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> dict:
    """Read records from a reviewed, profile-scoped health table."""
    return database().query(
        table,
        fields=fields,
        start=start,
        end=end,
        limit=limit,
        offset=offset,
    )


@mcp.tool()
def allos_metric_trend(
    metric: str,
    start: str,
    end: str,
) -> list[dict]:
    """Calculate daily minimum, maximum and average for up to 366 days inclusive."""
    return database().trend(metric, start, end)


def load_auth_token(path: str) -> bytes:
    """Load and validate a Bearer token from a secret file."""
    token = Path(path).read_bytes().strip()

    if len(token) < 32:
        raise ValueError(
            "Authentication token must contain at least 32 characters"
        )

    # HTTP Bearer tokens must be printable ASCII without whitespace.
    if any(byte < 33 or byte > 126 for byte in token):
        raise ValueError(
            "Authentication token contains invalid characters"
        )

    return token


class BearerAuth:
    """Pure ASGI middleware protecting the MCP HTTP endpoint."""

    def __init__(self, app: ASGIApp, token: bytes) -> None:
        self.app = app
        self.token = token

    async def __call__(
        self,
        scope: Scope,
        receive: Receive,
        send: Send,
    ) -> None:
        scope_type = scope["type"]

        # Preserve the MCP application's lifespan management.
        if scope_type == "lifespan":
            await self.app(scope, receive, send)
            return

        # MCP does not require WebSocket access.
        if scope_type == "websocket":
            await send({
                "type": "websocket.close",
                "code": 1008,
            })
            return

        if scope_type != "http":
            return

        auth_headers = [
            value
            for name, value in scope.get("headers", [])
            if name.lower() == b"authorization"
        ]

        authenticated = False

        # Reject missing or duplicate Authorization headers.
        if len(auth_headers) == 1:
            scheme, separator, supplied_token = (
                auth_headers[0].partition(b" ")
            )

            if separator and scheme.lower() == b"bearer":
                authenticated = hmac.compare_digest(
                    supplied_token,
                    self.token,
                )

        if not authenticated:
            body = b'{"error":"unauthorized"}'

            await send({
                "type": "http.response.start",
                "status": 401,
                "headers": [
                    (b"content-type", b"application/json"),
                    (b"www-authenticate", b"Bearer"),
                    (b"cache-control", b"no-store"),
                    (
                        b"content-length",
                        str(len(body)).encode("ascii"),
                    ),
                ],
            })

            await send({
                "type": "http.response.body",
                "body": body,
            })
            return

        await self.app(scope, receive, send)


def run_secure_http(
    host: str,
    port: int,
    token_path: str,
    cert_path: str,
    key_path: str,
) -> None:
    """Run authenticated MCP Streamable HTTP directly over TLS."""
    token = load_auth_token(token_path)

    mcp.settings.host = host
    mcp.settings.port = port

    # Preserve the SDK's own lifespan and session management.
    app = BearerAuth(
        mcp.streamable_http_app(),
        token,
    )

    config = uvicorn.Config(
        app=app,
        host=host,
        port=port,
        ssl_certfile=cert_path,
        ssl_keyfile=key_path,
        ssl_version=ssl.PROTOCOL_TLS_SERVER,
        proxy_headers=False,
        access_log=False,
        server_header=False,
    )

    # Load and validate the certificate and private key.
    config.load()

    if config.ssl is None:
        raise RuntimeError("TLS initialization failed")

    # Explicitly reject TLS versions older than TLS 1.2.
    config.ssl.minimum_version = ssl.TLSVersion.TLSv1_2

    server = uvicorn.Server(config)

    try:
        server.run()
    except KeyboardInterrupt:
        # A manual Ctrl+C is a normal shutdown, not an application error.
        pass


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Read-only Allos MCP server"
    )

    parser.add_argument(
        "--transport",
        choices=("stdio", "http"),
        default="stdio",
    )

    parser.add_argument(
        "--host",
        default="127.0.0.1",
    )

    parser.add_argument(
        "--port",
        type=int,
        default=8765,
    )

    parser.add_argument(
        "--allow-nonloopback",
        action="store_true",
        help="Explicitly permit listening outside loopback",
    )

    args = parser.parse_args()

    if not 1 <= args.port <= 65535:
        parser.error("Port must be between 1 and 65535")

    loopback_hosts = {
        "127.0.0.1",
        "::1",
        "localhost",
    }

    if (
        args.transport == "http"
        and args.host not in loopback_hosts
        and not args.allow_nonloopback
    ):
        parser.error(
            "Non-loopback HTTP requires --allow-nonloopback"
        )

    # Validate the database configuration before accepting clients.
    profile_id = os.environ.get("ALLOS_PROFILE_ID")

    if not profile_id:
        parser.error("ALLOS_PROFILE_ID is required")

    try:
        database().validate()
    except (ValueError, OSError, sqlite3.Error) as exc:
        parser.error(
            f"Invalid Allos database configuration: {exc}"
        )

    if args.transport == "stdio":
        # STDIO does not use the HTTP authentication layer.
        mcp.run(transport="stdio")
        return

    token_path = os.environ.get(
        "ALLOS_MCP_AUTH_TOKEN_FILE"
    )

    cert_path = os.environ.get(
        "ALLOS_MCP_TLS_CERT_FILE"
    )

    key_path = os.environ.get(
        "ALLOS_MCP_TLS_KEY_FILE"
    )

    if not all((token_path, cert_path, key_path)):
        parser.error(
            "HTTP transport requires "
            "ALLOS_MCP_AUTH_TOKEN_FILE, "
            "ALLOS_MCP_TLS_CERT_FILE and "
            "ALLOS_MCP_TLS_KEY_FILE"
        )

    try:
        run_secure_http(
            host=args.host,
            port=args.port,
            token_path=token_path,
            cert_path=cert_path,
            key_path=key_path,
        )
    except (OSError, ValueError, ssl.SSLError) as exc:
        parser.error(
            f"Invalid HTTP security configuration: {exc}"
        )


if __name__ == "__main__":
    main()
