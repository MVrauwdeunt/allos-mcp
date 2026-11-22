# Allos MCP Server

An **experimental, read-only** Model Context Protocol (MCP) integration for the self-hosted [Allos](https://github.com/FloorLamp/allos) health application.

> This is an independent community bridge, not an official Allos integration. Schema compatibility is based on a limited real-world installation and needs wider validation. Never commit real health databases or credentials.

## Features

- Official MCP Python SDK with **stdio** and **Streamable HTTP** transports.
- `allos_catalog`: list allowlisted profile-scoped tables and safe fields.
- `allos_metrics`: list metric types and row counts.
- `allos_read`: read up to 100 rows from reviewed tables, restricted to one configured profile.
- `allos_metric_trend`: daily summary of a metric (maximum 366 returned days).
- SQLite `mode=ro` and `PRAGMA query_only=ON`; no write operations or arbitrary SQL.
- Sensitive free-text columns, credentials, and unreviewed tables are excluded.

**Important:** These tools can still expose sensitive medical measurements to an MCP client and its AI provider. Use only with trusted clients and understand their data-handling policies.

## Install locally (stdio)

Requires Python 3.11+ and access to the Allos SQLite directory.

```bash
python3 -m venv .venv
.venv/bin/pip install -e .
ALLOS_DB_PATH=/var/lib/allos/allos.db ALLOS_PROFILE_ID=2 .venv/bin/allos-mcp
```

See [`examples/stdio-client.json`](examples/stdio-client.json). Set `ALLOS_PROFILE_ID` to the profile **you are authorized to access**. It is an access boundary selected by the administrator, not authentication for the MCP client.

## Local Streamable HTTP

```bash
ALLOS_DB_PATH=/var/lib/allos/allos.db ALLOS_PROFILE_ID=2 \
  .venv/bin/allos-mcp --transport http --host 127.0.0.1 --port 8765
```

Endpoint: `http://127.0.0.1:8765/mcp`.

**There is no HTTP authentication in this release. HTTP binds to loopback only.** For remote access, use an authenticated SSH tunnel as documented in [`examples/remote-over-ssh.md`](examples/remote-over-ssh.md). Do not expose it directly on public networks, LAN interfaces, or Tailscale interfaces.

## Container / Compose

```bash
podman build -t allos-mcp:local .
```

Set `ALLOS_DATA_DIR` (the directory containing `allos.db`) and `ALLOS_PROFILE_ID`, then run:

```bash
podman compose -f examples/compose.yaml up --build -d
```

The example binds to `0.0.0.0` **inside the container** but publishes only on the host's `127.0.0.1`. This requires the explicit `--allow-nonloopback` flag; do not publish the port to a non-loopback host interface. Mount the **whole directory** read-only, not just `allos.db`, to preserve WAL/SHM access. Set `ALLOS_UID` and `ALLOS_GID` to a UID/GID with access to the mounted directory; do not change permissions on the real medical data solely for this integration.

## Tests

```bash
python3 -m venv .venv
.venv/bin/pip install -e '.[test]'
.venv/bin/pytest -q
```

Tests use synthetic data, not real health records.

## Compatibility and security limitations

- Database schema changes between Allos versions may affect tool availability.
- Generic tools work only for tables that contain a `profile_id` column and are on the reviewed allowlist.
- Only approved column names are selected. Client-provided SQL or query expressions are never accepted.
- There is currently no multi-user authorization, audit log, rate limiting or authenticated HTTP endpoint.
- Treat a separate MCP process/profile as a separate trust boundary. A malicious or compromised MCP client may request all approved measurements for that profile.
- Allos's source license is separate from this project's MIT license; this repository contains no Allos source code.
- The `mcp` dependency is restricted to SDK v1. Validate SDK upgrades before release.

## Roadmap

1. Test against multiple Allos schema versions.
2. Add optional authenticated HTTP behind a security review.
3. Publish GHCR image with CI and vulnerability scanning.
4. Add optional NixOS packaging and MCP Registry metadata once stable.

## License

MIT. See [LICENSE](LICENSE).
