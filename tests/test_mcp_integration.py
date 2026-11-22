
"""Exercise the real MCP stdio protocol against synthetic health data."""

import asyncio
import json
import os
import sys

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


EXPECTED_TOOLS = {
    "allos_catalog",
    "allos_metrics",
    "allos_read",
    "allos_metric_trend",
}


def _payload(result):
    """Extract tool data from MCP structured or text content."""
    assert not result.isError, result

    if result.structuredContent is not None:
        data = result.structuredContent
    else:
        texts = [
            part.text
            for part in result.content
            if part.type == "text"
        ]

        assert texts, "Expected a JSON response from the MCP tool"
        data = json.loads(texts[0])

    # FastMCP may wrap list results in a {"result": [...]} object.
    if isinstance(data, dict) and set(data) == {"result"}:
        return data["result"]

    return data


def test_real_stdio_mcp_client(sample_database):
    """Verify all MCP tools using a real stdio client and synthetic data."""

    async def check():
        params = StdioServerParameters(
            command=sys.executable,
            args=["-m", "allos_mcp"],
            env={
                **os.environ,
                "ALLOS_DB_PATH": str(sample_database),
                "ALLOS_PROFILE_ID": "1",
            },
        )

        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                initialized = await session.initialize()

                assert initialized.serverInfo.name == "allos-mcp"
                assert initialized.serverInfo.version == "0.1.1"

                tools = await session.list_tools()

                assert {
                    tool.name for tool in tools.tools
                } == EXPECTED_TOOLS

                # Discover readable tables.
                catalog = _payload(
                    await session.call_tool("allos_catalog", {})
                )

                assert "metric_samples" in {
                    row["table"] for row in catalog
                }

                assert "api_tokens" not in {
                    row["table"] for row in catalog
                }

                # Discover available metrics.
                metrics = _payload(
                    await session.call_tool("allos_metrics", {})
                )

                assert metrics == [
                    {
                        "metric": "weight",
                        "sample_count": 2,
                    }
                ]

                # Query only the configured profile.
                readings = _payload(
                    await session.call_tool(
                        "allos_read",
                        {
                            "table": "metric_samples",
                            "fields": ["profile_id", "value"],
                            "limit": 10,
                        },
                    )
                )

                assert readings["count_returned"] == 2

                assert {
                    row["profile_id"]
                    for row in readings["rows"]
                } == {1}

                assert {
                    row["value"]
                    for row in readings["rows"]
                } == {75.0, 76.0}

                # Calculate trends without leaking another profile's data.
                trend = _payload(
                    await session.call_tool(
                        "allos_metric_trend",
                        {
                            "metric": "weight",
                            "start": "2026-11-01",
                            "end": "2026-11-30",
                        },
                    )
                )

                assert sum(
                    row["samples"] for row in trend
                ) == 2

                assert all(
                    row["maximum"] < 99
                    for row in trend
                )

    asyncio.run(asyncio.wait_for(check(), timeout=20))
