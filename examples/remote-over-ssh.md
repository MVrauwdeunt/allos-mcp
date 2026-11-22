# Remote MCP access

By default, this package exposes HTTP only on the **local loopback interface** and has **no HTTP authentication**. Do not bind it to `0.0.0.0` or a Tailnet/LAN address without a separately implemented and reviewed authentication layer.

For a remote client with an SSH connection to the Allos host:

```bash
ssh -N -L 8765:127.0.0.1:8765 allos-host
```

Point the MCP client to `http://127.0.0.1:8765/mcp` while the tunnel is active. This makes access depend on SSH authentication without introducing a public MCP endpoint.

Do not forward the port to the public internet. Health records are sensitive and MCP tools may send results to the configured AI provider.
