
# Allos MCP Server

[![CI](https://github.com/MVrauwdeunt/allos-mcp/actions/workflows/ci.yml/badge.svg)](https://github.com/MVrauwdeunt/allos-mcp/actions/workflows/ci.yml)
[![Container publishing](https://github.com/MVrauwdeunt/allos-mcp/actions/workflows/publish.yml/badge.svg)](https://github.com/MVrauwdeunt/allos-mcp/actions/workflows/publish.yml)

An **unofficial, experimental, read-only [Model Context Protocol (MCP)](https://modelcontextprotocol.io/)** server for the self-hosted [Allos](https://github.com/FloorLamp/allos) personal health application.

Allos MCP exposes selected structured health measurements to compatible AI assistants without changing Allos, copying data to a second database, or requiring a cloud synchronization service.

> **Privacy:** The server is read-only, but connected AI clients can retrieve sensitive health data and may forward it to their model providers. Only connect trusted clients. Do not expose the unauthenticated HTTP endpoint publicly.
>
> **Compatibility:** Tested against a limited Allos database schema and synthetic test fixtures. Not affiliated with or endorsed by the Allos maintainers.

## Why does this exist?

Allos has a token-authenticated HTTP API for certain document integrations, but its current API does **not** expose general read endpoints for health measurements. Allos MCP fills that gap by reading selected measurements directly from Allos's SQLite database.

| Capability | Allos MCP | Existing Allos API |
| --- | --- | --- |
| Read supported health measurements | Yes | No general measurement read endpoint |
| Filter readings by date and paginate | Yes | No general measurement read endpoint |
| Summarize daily numeric trends | Yes | No general measurement read endpoint |
| Discover supported health metrics | Yes | No general measurement read endpoint |
| Upload documents | No | Yes, with the appropriate API capability |
| Create, edit, or delete health measurements | No | Not supported by the documented document API |

Examples of questions an MCP client might answer, if the data is available and allowlisted:

- "How has my weight changed over the past three months?"
- "What blood pressure readings do I have from last month?"
- "Compare my recorded measurements from January and June."

The MCP server returns data and simple aggregates. Interpretation is performed by your MCP client or AI model; it is **not** medical advice.

## Features

- Official Python MCP SDK, with **stdio** and **Streamable HTTP** transports.
- SQLite opened read-only (`mode=ro`, `PRAGMA query_only=ON`).
- Explicit table/column restrictions and an administrator-configured `ALLOS_PROFILE_ID`.
- No client-supplied SQL, database writes, or credential access.
- Four MCP tools:

| Tool | Purpose |
| --- | --- |
| `allos_catalog` | Show approved tables and accessible columns |
| `allos_metrics` | List available metric names and sample counts |
| `allos_read` | Read approved records, with date filters and pagination (up to 100 per request) |
| `allos_metric_trend` | Daily count, minimum, maximum and mean for a numeric metric |

Only allowlisted tables with a `profile_id` column can be read. Coverage depends on the installed Allos schema; some categories of health data are intentionally unavailable.

## Requirements

- Python **3.11+** for a source installation, or Docker/Podman for containers.
- Filesystem read permissions on the **Allos SQLite database directory**.
- The relevant Allos `profile_id` (a server setting, **not** a client authentication mechanism).

The database path in examples is illustrative; it may differ in your installation. Use the **entire SQLite directory**, not just a single file, to account for `-wal` and `-shm` sidecar files. Never make a health database world-readable to work around permissions.

## Install using a published GHCR image

> **Availability:** These commands work once the maintainers have published the first GHCR package and made it public. Until then, use [Build a local container image](#build-a-local-container-image) below. No image is claimed to exist before its successful release.

The canonical image name is `ghcr.io/mvrauwdeunt/allos-mcp`.

- `:edge` tracks the latest successfully built `main` commit and may change at any time.
- `:0.1.0`, `:0.2.0`, and similar tags are release versions, created from `v*` Git tags once these tags are mirrored to GitHub.
- `:sha-...` identifies a source commit.

Pull a published version (replace `0.1.0` with a tag actually listed in [GitHub Packages](https://github.com/users/MVrauwdeunt/packages/container/package/allos-mcp)):

```bash
podman pull ghcr.io/mvrauwdeunt/allos-mcp:0.1.0
```

Start the server on the machine that can access your Allos database:

```bash
podman run -d --name allos-mcp --restart unless-stopped \
  -p 127.0.0.1:8765:8765 \
  -v /path/to/allos-data:/data:ro \
  -e ALLOS_DB_PATH=/data/allos.db \
  -e ALLOS_PROFILE_ID=1 \
  ghcr.io/mvrauwdeunt/allos-mcp:0.1.0 \
  --transport http --host 0.0.0.0 --port 8765 --allow-nonloopback
```

Replace the directory, profile ID, and tag with your actual values. The container normally runs as UID **10001**; its user must have read permission for the directory and database. Docker users can replace `podman` with `docker`.

**Networking:** `0.0.0.0` is only the *container-internal* listener. `-p 127.0.0.1:8765:8765` ensures the host only publishes it locally. `--allow-nonloopback` disables a bind-address safety check; it **does not** add authentication. Never publish this port on all host interfaces without a separately secured gateway.

### Docker Compose or Podman Compose

The checked-in [`examples/compose.yaml`](examples/compose.yaml) uses the GHCR image instead of rebuilding from source:

```bash
export ALLOS_DATA_DIR=/path/to/allos-data
export ALLOS_PROFILE_ID=1
export ALLOS_VERSION=0.1.0

# Override only if the container UID/GID cannot read the database directory:
# export ALLOS_UID=1000 ALLOS_GID=1000

docker compose -f examples/compose.yaml up -d
```

For Podman, use `podman compose` with an installed Compose provider. Check permissions carefully before changing the container user. While no release is available, set `ALLOS_VERSION=edge` **only after** the `edge` image exists, or use the local build instructions below.

## Build a local container image

This method works before any GHCR image is published:

```bash
git clone https://github.com/MVrauwdeunt/allos-mcp.git
cd allos-mcp
podman build -t allos-mcp:local -f Containerfile .
```

Run the locally built image:

```bash
podman run -d --name allos-mcp --restart unless-stopped \
  -p 127.0.0.1:8765:8765 \
  -v /path/to/allos-data:/data:ro \
  -e ALLOS_DB_PATH=/data/allos.db \
  -e ALLOS_PROFILE_ID=1 \
  localhost/allos-mcp:local \
  --transport http --host 0.0.0.0 --port 8765 --allow-nonloopback
```

For a temporary test, replace `-d --restart unless-stopped` with `--rm`. Do not run two containers mapped to the same host port simultaneously.

## Install from Python source (local stdio)

Stdio is a good choice when the MCP client runs on the same machine as the SQLite files:

```bash
git clone https://github.com/MVrauwdeunt/allos-mcp.git
cd allos-mcp
python3 -m venv .venv
.venv/bin/python -m pip install .
.venv/bin/allos-mcp --help
```

Example MCP client configuration (use actual absolute paths):

```json
{
  "mcpServers": {
    "allos": {
      "command": "/opt/allos-mcp/.venv/bin/allos-mcp",
      "args": ["--transport", "stdio"],
      "env": {
        "ALLOS_DB_PATH": "/var/lib/allos/allos.db",
        "ALLOS_PROFILE_ID": "1"
      }
    }
  }
}
```

Stdio clients launch the process themselves. See [`examples/stdio-client.json`](examples/stdio-client.json). The package is not yet published to PyPI: `pip install allos-mcp` without a local source checkout is not a supported installation method yet.

## Local HTTP without a container

```bash
ALLOS_DB_PATH=/var/lib/allos/allos.db \
ALLOS_PROFILE_ID=1 \
  .venv/bin/allos-mcp --transport http --host 127.0.0.1 --port 8765
```

Endpoint: `http://127.0.0.1:8765/mcp`. This endpoint has **no built-in HTTP authentication**.

## Remote client access over SSH

For a client on another computer, keep HTTP bound to `127.0.0.1` on the Allos MCP host and open a tunnel **from the client computer**:

```bash
ssh -N -L 18765:127.0.0.1:8765 user@allos-server
```

Configure the MCP client to use `http://127.0.0.1:18765/mcp`. The tunnel requires a working SSH account and runs while the SSH session remains open. The forwarded port is accessible to suitable local processes; SSH alone does not implement per-MCP-client authorization. See [`examples/remote-over-ssh.md`](examples/remote-over-ssh.md).

## Verify that the HTTP endpoint works

A plain GET may return `400 Bad Request: Missing session ID`; that alone does not mean the container is broken. Initialize a session instead:

```bash
curl -si --max-time 10 http://127.0.0.1:8765/mcp \
  -H 'Content-Type: application/json' \
  -H 'Accept: application/json, text/event-stream' \
  -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-11-25","capabilities":{},"clientInfo":{"name":"curl-test","version":"1.0"}}}'
```

Expected: HTTP `200`, an `mcp-session-id` response header, and a JSON-RPC `initialize` result. To call tools, use an MCP-aware client that completes the session handshake.

## Development and CI

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -e '.[test]'
.venv/bin/python -m pytest -q
```

Tests use synthetic fixtures, not real medical records.

- [CI workflow](.github/workflows/ci.yml): tests for Python 3.11–3.13, package build, container build.
- [Publish workflow](.github/workflows/publish.yml): re-runs tests, builds `linux/amd64` and `linux/arm64`, and publishes to GHCR using the GitHub Actions `GITHUB_TOKEN` after a `main` push, mirrored release tag, or manual dispatch.
- **Forgejo is the source of truth.** Development pushes to Forgejo; GitHub is a one-way mirror and is used for GitHub Actions/GHCR publishing. Tags must reach GitHub for versioned releases.

### Maintainer: publishing a new container version

1. Confirm tests pass and the Forgejo → GitHub mirror has successfully synchronized `main`.
2. Verify the GHCR publish workflow succeeds for `main` and produces `:edge`.
3. Make the GHCR package public under GitHub package settings if anonymous pulls are desired.
4. Ensure the Forgejo mirror also synchronizes **Git tags**; a `main`-only branch filter may prevent this.
5. Create an annotated release tag in the Forgejo checkout:

   ```bash
   git tag -a v0.1.0 -m "Allos MCP v0.1.0"
   git push origin v0.1.0
   ```

6. Confirm tag `v0.1.0` exists on GitHub and the publish workflow produced `ghcr.io/mvrauwdeunt/allos-mcp:0.1.0`.
7. Pull and test the published image before announcing the release.

**Note:** Git push mirroring synchronizes Git refs, not GitHub Releases, release attachments, or package visibility. Version tags and published packages are separate things.

## Security and current limitations

- Experimental integration, not a hardened medical-record API.
- **No HTTP authentication**, per-client authorization, audit logging, or rate limiting.
- The server uses one administrator-selected profile ID. Connected clients may read all **allowlisted** data for that profile, within per-query limits; the limits do not prevent repeated requests.
- No arbitrary SQL, writes, record deletion, or document upload.
- Only allowlisted tables and columns are exposed. Not all medication, diagnosis, narrative, or document data is available.
- Read-only database access prevents modifications **through this integration**, but does not prevent data disclosure to clients or model providers.
- Schema compatibility may change when Allos is upgraded; review and retest against the new schema.
- This MIT-licensed project is independent of Allos and does not bundle Allos source code.

## Roadmap

- Validate additional Allos schema versions.
- Add more synthetic compatibility and permission tests.
- Evaluate authenticated HTTP access and audit logging.
- Improve package distribution and release automation.

## License

MIT. See [LICENSE](LICENSE).
