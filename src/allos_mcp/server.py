"""Public Allos MCP entrypoint built on the official MCP Python SDK."""
import argparse
import os
from functools import lru_cache
from importlib.metadata import version
from mcp.server.fastmcp import FastMCP
from .db import AllosDB

mcp = FastMCP("allos-mcp", json_response=True, host="127.0.0.1", port=8765)
# Report the Allos MCP package version instead of the MCP SDK version.
mcp._mcp_server.version = version("allos-mcp")

@lru_cache(maxsize=1)
def database() -> AllosDB:
    return AllosDB(
        os.environ.get("ALLOS_DB_PATH", "/data/allos.db"),
        int(os.environ["ALLOS_PROFILE_ID"]),
    )


@mcp.tool()
def allos_catalog() -> list[dict]:
    """List reviewed Allos health tables and their readable columns for the configured profile."""
    return database().catalog()


@mcp.tool()
def allos_metrics() -> list[dict]:
    """List available metric names and counts, scoped to the configured Allos profile."""
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
    """Read up to 100 records from a reviewed profile-scoped table; SQL input is forbidden."""
    return database().query(table, fields=fields, start=start, end=end, limit=limit, offset=offset)


@mcp.tool()
def allos_metric_trend(metric: str, start: str, end: str) -> list[dict]:
    """Calculate daily minimum, maximum and average of a named metric over an ISO date range."""
    return database().trend(metric, start, end)


def main() -> None:
    parser = argparse.ArgumentParser(description="Read-only Allos MCP server")
    parser.add_argument("--transport", choices=("stdio", "http"), default="stdio")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--allow-nonloopback", action="store_true", help="Required for container networking; provide external access controls")
    args = parser.parse_args()

    # Fail before accepting clients if the database/profile are missing.
    database()
    if args.transport == "http":
        if args.host not in ("127.0.0.1", "::1", "localhost") and not args.allow_nonloopback:
            parser.error("Non-loopback HTTP requires --allow-nonloopback and external access controls")
        if not 1 <= args.port <= 65535:
            parser.error("Invalid port")
        mcp.settings.host = args.host
        mcp.settings.port = args.port
        mcp.run(transport="streamable-http")
    else:
        mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
