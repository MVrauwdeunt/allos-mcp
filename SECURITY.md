# Security Policy

Allos MCP is an independent, experimental, read-only Model Context Protocol (MCP) server for the self-hosted [Allos](https://github.com/FloorLamp/allos) personal health application.

Security and privacy are important because this project provides access to potentially sensitive personal health information.

This document describes the project's security model, known limitations, recommended deployment practices, and vulnerability reporting process.

## Supported Versions

Security fixes are provided on a best-effort basis.

| Version | Security support |
| --- | --- |
| Latest release | ✅ Best-effort security updates |
| `edge` / `main` | Development branch, not guaranteed stable |
| Older releases | ❌ No guaranteed security updates |

Users are encouraged to use the latest stable release and review release notes before upgrading.

## Security Model

Allos MCP is designed around restricted, read-only access to an existing Allos SQLite database.

### Implemented protections

- **Read-only SQLite access:** Database connections use SQLite read-only mode and `PRAGMA query_only=ON`.
- **Explicit table restrictions:** Only reviewed database tables can be queried.
- **Restricted fields:** Known sensitive columns are excluded from tool responses.
- **Profile scoping:** Queries are restricted to an administrator-configured `ALLOS_PROFILE_ID`.
- **No arbitrary SQL:** MCP clients cannot submit SQL statements directly.
- **Input validation:** Query limits, pagination, dates, table names, and column selections are validated.
- **Restricted HTTP binding:** Listening on non-loopback interfaces requires an explicit `--allow-nonloopback` override.
- **Automated regression tests:** Tests cover profile isolation, read-only access, query validation, MCP protocol behavior, HTTP binding, and selected schema compatibility scenarios.

These measures reduce the risk of unintended access or modification. They do not guarantee complete protection against all vulnerabilities.

## Known Security Limitations

### No built-in HTTP authentication

Allos MCP currently does not provide:

- HTTP authentication or API tokens.
- Per-client authorization.
- Request rate limiting.
- Security audit logging.
- Built-in TLS termination.

**Anyone who can reach the MCP HTTP endpoint may be able to query the health data available to that server instance.**

The `--allow-nonloopback` option is not an authentication mechanism. It only permits the server to bind to an address other than loopback.

Never expose the MCP endpoint directly to the public internet or untrusted networks.

### Profile ID is not authentication

`ALLOS_PROFILE_ID` selects the Allos profile accessible to an MCP server instance.

It is not an authentication credential and does not provide per-client access control.

All clients connected to the same instance can potentially access the same approved data.

### Read-only does not mean confidential

Read-only operation prevents the MCP integration from modifying the database.

It does not prevent connected clients from retrieving or disclosing approved health data.

An AI assistant may forward retrieved measurements to its configured AI provider.

Users are responsible for understanding the privacy policies and data-handling practices of their MCP clients and model providers.

### Direct SQLite access

Allos MCP accesses the SQLite database directly rather than using Allos' application-level authorization or HTTP API.

As a result:

- Allos' normal authentication does not protect the MCP endpoint.
- Database schema changes may affect compatibility.
- Profile isolation relies on the MCP implementation.
- Filesystem permissions are an important security boundary.

The current field filtering is not a guarantee that every sensitive column introduced by a future Allos schema change will automatically be excluded.

## Recommended Deployment

### 1. Keep HTTP access local

Bind the published container port to `127.0.0.1`:

```bash
-p 127.0.0.1:8765:8765
```

Inside a container, the MCP process may need to listen on `0.0.0.0` for port forwarding to work.

This does not mean the host port should be publicly exposed.

For non-container installations, prefer:

```bash
allos-mcp --transport http --host 127.0.0.1
```

### 2. Use a trusted transport for remote clients

For remote MCP access, prefer an authenticated SSH tunnel:

```bash
ssh -N -L 18765:127.0.0.1:8765 user@allos-server
```

The MCP client can then connect to:

```text
http://127.0.0.1:18765/mcp
```

SSH protects the network connection, but it does not provide per-MCP-client authorization. Processes able to access the forwarded local port may also reach the service.

Do not assume that a private network or VPN automatically provides sufficient application-level authorization.

### 3. Mount the database read-only

For container deployments:

```bash
-v /path/to/allos-data:/data:ro
```

Mount the complete SQLite directory, including any WAL and SHM files.

The container process requires appropriate filesystem read permissions.

Do not make the database world-readable to work around permission problems.

Use a dedicated, minimally privileged account where practical.

### 4. Protect the host and database

- Apply operating system and container runtime security updates.
- Restrict access to the Allos database directory.
- Avoid privileged containers.
- Avoid unnecessary host filesystem mounts.
- Do not store credentials or personal health databases in the source repository.
- Review dependency and image updates before deploying them.
- Treat database backups as sensitive health information.

### 5. Use trusted MCP clients

Only connect clients you trust.

Before connecting an AI assistant, consider whether the provider may store or process retrieved health information.

If you do not want health data sent to a third-party AI service, use a client and model configuration that keeps processing within your trusted environment.

## Reporting a Vulnerability

**Please do not publicly disclose an unpatched security vulnerability in a GitHub Issue, Discussion, or Pull Request.**

Report security vulnerabilities privately through GitHub's security advisory system, if enabled:

[Report a vulnerability](https://github.com/MVrauwdeunt/allos-mcp/security/advisories/new)

If private vulnerability reporting is unavailable, open a public issue requesting a private contact method **without including vulnerability details, exploit code, or sensitive information**.

When reporting a vulnerability, include where possible:

- A description of the issue and its potential impact.
- The affected Allos MCP version.
- Relevant deployment information.
- Reproduction steps using synthetic data.
- Relevant logs with secrets and health information removed.

Never submit real medical records, database files, credentials, or other personal information as part of a vulnerability report.

## Disclosure and Response

Security reports are handled on a best-effort basis.

The maintainer will aim to:

1. Review and acknowledge valid reports.
2. Reproduce the issue using synthetic test data.
3. Assess the security impact.
4. Develop and test an appropriate fix.
5. Publish a security advisory or release where necessary.
6. Credit the reporter when appropriate and agreed.

No guaranteed response or remediation timeline is currently offered.

Coordinated disclosure is appreciated.

## Security Testing

The project includes automated tests for:

- SQLite read-only enforcement.
- Profile isolation.
- Sensitive field restrictions.
- SQL injection resistance in supported query interfaces.
- Date and pagination validation.
- MCP tool discovery and invocation through STDIO.
- HTTP loopback binding and initialization.
- Selected database schema changes.

These tests provide regression coverage but are not equivalent to an independent penetration test or formal security audit.

## Scope

This policy covers vulnerabilities in the Allos MCP project itself.

For vulnerabilities affecting the upstream Allos application, please consult the [Allos repository](https://github.com/FloorLamp/allos) and its security reporting instructions.

Allos MCP is an independent community project and is not affiliated with or endorsed by the Allos maintainers.

## License

Allos MCP's current development branch is licensed under **AGPL-3.0-only**.

Earlier published versions may use different license terms. Refer to the `LICENSE` file associated with the specific release.