
# Allos MCP Server

[![CI](https://github.com/MVrauwdeunt/allos-mcp/actions/workflows/ci.yml/badge.svg)](https://github.com/MVrauwdeunt/allos-mcp/actions/workflows/ci.yml)
[![Container publishing](https://github.com/MVrauwdeunt/allos-mcp/actions/workflows/publish.yml/badge.svg)](https://github.com/MVrauwdeunt/allos-mcp/actions/workflows/publish.yml)

An unofficial, experimental, read-only Model Context Protocol
(MCP) server for the self-hosted
[Allos](https://github.com/FloorLamp/allos)
personal health application.

Allos MCP provides selected structured health measurements
to compatible AI assistants.

The server reads directly from an existing Allos SQLite database.
It does not modify the database or require cloud synchronization.

> **Privacy:** Connected AI clients may retrieve sensitive personal
> health information. Only connect trusted clients and review
> how their model providers process retrieved data.

> **Compatibility:** This project is independent of Allos and
> has been tested against a limited selection of database schemas.
> It is not affiliated with or endorsed by the Allos maintainers.

## Features

- Official Python MCP SDK.
- STDIO and Streamable HTTP transports.
- Direct HTTPS support without a reverse proxy.
- Bearer-token authentication for HTTP connections.
- TLS certificate verification by MCP clients.
- Read-only SQLite database access.
- Explicit table and field restrictions.
- Profile-scoped queries.
- Automated security and integration tests.
- Docker/Podman container support.
- Linux AMD64 and ARM64 container images.

## MCP tools

| Tool | Description |
| --- | --- |
| `allos_catalog` | Discover approved tables and available fields |
| `allos_metrics` | Discover available health metrics |
| `allos_read` | Read approved profile-scoped health records |
| `allos_metric_trend` | Calculate daily metric trends |

The database backend restricts which tables and fields can be
queried.

Clients cannot submit arbitrary SQL statements.

The MCP server does not provide write operations.

## Requirements

- Python 3.11 or newer for source installations.
- An existing Allos SQLite database.
- Read permissions on the complete database directory.
- A valid Allos profile ID.
- OpenSSL for generating local test certificates.

For HTTPS installations:

- A cryptographically random Bearer token.
- A TLS server certificate.
- The corresponding TLS private key.
- A client that supports custom HTTP authorization headers
  and certificate verification.

## Installation from source

Clone the repository:

```bash
git clone https://github.com/MVrauwdeunt/allos-mcp.git
cd allos-mcp
```

Create a Python environment:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install .
```

### STDIO mode

STDIO is the default transport.

```bash
ALLOS_DB_PATH=/path/to/allos.db \
ALLOS_PROFILE_ID=1 \
  .venv/bin/allos-mcp
```

STDIO does not use HTTP authentication or TLS because the
MCP client communicates with a locally launched process.

Example client configuration:

```json
{
  "mcpServers": {
    "allos": {
      "command": "/opt/allos-mcp/.venv/bin/allos-mcp",
      "env": {
        "ALLOS_DB_PATH": "/path/to/allos.db",
        "ALLOS_PROFILE_ID": "1"
      }
    }
  }
}
```

## Secure HTTPS mode

HTTP transport requires both TLS and Bearer authentication.

Allos MCP provides HTTPS directly through its Python server.
A reverse proxy is not required.

### Generate a token

For local development:

```bash
mkdir -p .local/secrets
chmod 700 .local/secrets

openssl rand -hex 32 > .local/secrets/token
chmod 600 .local/secrets/token
```

### Generate a local test certificate

```bash
openssl req -x509 -newkey rsa:3072 -sha256 \
  -nodes \
  -days 30 \
  -keyout .local/secrets/server.key \
  -out .local/secrets/server.crt \
  -subj "/CN=localhost" \
  -addext "subjectAltName=DNS:localhost,IP:127.0.0.1"

chmod 600 .local/secrets/server.key
```

This certificate is intended only for local development.

For remote deployment, use a certificate with a subjectAltName
matching the DNS name or IP address used by the MCP client.

The client must trust the issuing certificate authority or
the explicitly trusted self-signed server certificate.

Never disable certificate verification to work around
a certificate mismatch.

### Configure the server

```bash
export ALLOS_DB_PATH="/path/to/allos.db"
export ALLOS_PROFILE_ID=1

export ALLOS_MCP_AUTH_TOKEN_FILE="$PWD/.local/secrets/token"
export ALLOS_MCP_TLS_CERT_FILE="$PWD/.local/secrets/server.crt"
export ALLOS_MCP_TLS_KEY_FILE="$PWD/.local/secrets/server.key"
```

Start the server:

```bash
.venv/bin/allos-mcp \
  --transport http \
  --host 127.0.0.1 \
  --port 8765
```

Endpoint:

```text
https://127.0.0.1:8765/mcp
```

HTTP requests without a valid token receive HTTP 401.

A valid token does not bypass database restrictions.

### Test authentication

Without a token:

```bash
curl --cacert .local/secrets/server.crt \
  -i https://localhost:8765/mcp
```

Expected:

```text
HTTP/1.1 401 Unauthorized
```

With an invalid token:

```bash
curl --cacert .local/secrets/server.crt \
  -i \
  -H 'Authorization: Bearer invalid-token' \
  https://localhost:8765/mcp
```

Expected: HTTP 401.

With the configured token:

```bash
curl --cacert .local/secrets/server.crt \
  -i \
  -H "Authorization: Bearer $(cat .local/secrets/token)" \
  https://localhost:8765/mcp
```

A plain GET may return an MCP protocol response such as
HTTP 406 because the request does not contain the necessary
MCP headers.

A successful authorization test must not return HTTP 401.

Use an actual MCP client to test initialization and tool calls.

## Container deployment

Published images use:

```text
ghcr.io/mvrauwdeunt/allos-mcp
```

Image tags:

- `edge`: latest successfully published development image.
- `0.1.2`: previous stable release.
- `0.2.0`: secure release, once published.
- `sha-*`: images associated with specific commits.

### Build locally

Before the secure version is released, build from the
development branch:

```bash
podman build \
  -t localhost/allos-mcp:secure-test \
  -f Containerfile .
```

### Run with Podman

```bash
podman run --rm \
  --name allos-mcp \
  -p 127.0.0.1:8765:8765 \
  -v /path/to/allos-data:/data:ro \
  -v /path/to/allos-mcp-secrets:/run/secrets:ro \
  -e ALLOS_DB_PATH=/data/allos.db \
  -e ALLOS_PROFILE_ID=1 \
  -e ALLOS_MCP_AUTH_TOKEN_FILE=/run/secrets/token \
  -e ALLOS_MCP_TLS_CERT_FILE=/run/secrets/server.crt \
  -e ALLOS_MCP_TLS_KEY_FILE=/run/secrets/server.key \
  localhost/allos-mcp:secure-test \
  --transport http \
  --host 0.0.0.0 \
  --port 8765 \
  --allow-nonloopback
```

Replace all example paths and the profile ID.

The entire SQLite directory must be mounted, including
any WAL and SHM sidecar files.

The container user must have permission to read the mounted
database, token and certificate files.

### Docker Compose / Podman Compose

Use:

```text
examples/compose.yaml
```

Copy the provided configuration example:

```bash
cp examples/.env.example examples/.env
```

Edit the configuration with the actual paths and profile ID.

For a local development image, change the Compose image
reference to:

```yaml
image: localhost/allos-mcp:secure-test
```

Then start:

```bash
podman compose \
  --env-file examples/.env \
  -f examples/compose.yaml \
  up -d
```

The configuration publishes port 8765 on host loopback
by default.

To connect from another machine, explicitly configure
`ALLOS_BIND_ADDRESS` for the intended host interface.

The HTTPS certificate must match the address used by
the remote MCP client.

Never publish the MCP endpoint to untrusted networks
without reviewing access controls and exposure.

## Environment variables

| Variable | Description |
| --- | --- |
| `ALLOS_DB_PATH` | Path to the Allos SQLite database |
| `ALLOS_PROFILE_ID` | Profile ID accessible through the MCP instance |
| `ALLOS_MCP_AUTH_TOKEN_FILE` | Bearer-token file for HTTPS |
| `ALLOS_MCP_TLS_CERT_FILE` | TLS server certificate file |
| `ALLOS_MCP_TLS_KEY_FILE` | TLS private key file |

HTTP transport requires the three security file variables.

STDIO transport does not require these HTTP settings.

## Security model

Allos MCP uses multiple independent protections:

1. TLS protects data in transit.
2. Bearer authentication controls HTTP access.
3. Profile scoping limits database access.
4. Table and column restrictions limit exposed information.
5. SQLite connections are read-only.
6. MCP clients cannot submit arbitrary SQL.

These protections do not guarantee that retrieved health
information remains private after it reaches an MCP client.

Bearer tokens are shared secrets, not user identities.

The server currently has no per-client roles, built-in
token revocation API, audit trail or rate limiting.

For additional details, see [SECURITY.md](SECURITY.md).

## Limitations

- Only reviewed database tables are supported.
- Not all Allos health data categories are exposed.
- Schema changes may affect compatibility.
- A single MCP instance is scoped to one configured profile.
- HTTP clients with the valid token can access the approved
  data for that instance.
- Direct SQLite access is independent of Allos application
  sessions and application-level permissions.
- The server does not provide medical advice.

## Development and testing

Install development dependencies:

```bash
python -m pip install -e '.[test]'
```

Run tests:

```bash
python -m pytest -q
```

Check Python syntax:

```bash
python -m compileall -q src/allos_mcp
```

The tests use synthetic SQLite data.

The HTTPS tests generate short-lived test certificates
and verify authenticated MCP initialization and tool calls.

CI runs on Python 3.11, 3.12 and 3.13.

## Repository and releases

Forgejo is the primary Git repository.

GitHub is used as a public mirror for source distribution,
GitHub Actions and GHCR container publishing.

The publishing workflow builds Linux AMD64 and ARM64 images.

Development tags and stable release tags must be validated
before publication.

## Roadmap

- Improve schema compatibility across Allos releases.
- Expand authorized read-only metric coverage.
- Improve operational security and token rotation.
- Evaluate an optional official Allos Device API backend.
- Consider standards-based OAuth authorization if needed
  for more complex client deployments.

## License

Allos MCP is licensed under
**GNU Affero General Public License v3.0 only
(AGPL-3.0-only)**.

See [LICENSE](LICENSE).

Earlier releases may use different license terms.
Consult the license associated with each release.

This is an independent community project.
Allos is developed separately by its maintainers.
```
