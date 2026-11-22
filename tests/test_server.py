from allos_mcp.server import mcp


def test_tool_registry():
    # SDK wiring must register all four public tools.
    import asyncio
    names = {tool.name for tool in asyncio.run(mcp.list_tools())}
    assert names == {"allos_catalog", "allos_metrics", "allos_read", "allos_metric_trend"}
