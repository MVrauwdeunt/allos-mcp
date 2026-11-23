
# Security Policy

Allos MCP is an independent, experimental, read-only
Model Context Protocol (MCP) server for the self-hosted
Allos personal health application.

The project may provide access to sensitive personal
health information.

This policy describes supported versions, security
controls, deployment recommendations, known limitations
and vulnerability reporting.

## Supported Versions

Security updates are provided on a best-effort basis.

| Version | Support |
| --- | --- |
| Latest stable release | Best-effort security fixes |
| `main` / `edge` | Development, no stability guarantee |
| Older releases | No guaranteed security fixes |

Users should review release notes before upgrading.

The HTTPS and Bearer-token protections described below
apply to the secure development version intended for v0.2.0.

Earlier releases, including v0.1.2, do not provide the
same built-in HTTP security controls.

## Security Architecture

The project provides two MCP transports.

### STDIO

STDIO is intended for local MCP clients launching the server
as a subprocess.

It does not expose an HTTP endpoint.

Access depends on operating system permissions and the
security of the local client process.

### Streamable HTTP over HTTPS

The secure HTTP transport requires:

- TLS server certificate.
- TLS private key.
- Bearer authentication token.
- Explicit server configuration.

The HTTP server refuses to start when these required
security settings are missing.

Authentication is checked before requests enter the
MCP protocol handler.

All HTTP requests, including follow-up requests within
an MCP session, require authorization.

A missing, malformed or incorrect token is rejected
with HTTP 401.

The server uses the existing Python/Uvicorn HTTP implementation
with native TLS support.

A reverse proxy or separate authentication service
is not required.

## Implemented Protections

### Read-only SQLite access

The Allos database is opened in read-only mode.

SQLite query-only restrictions prevent modification
through this integration.

### Table and field restrictions

Only reviewed tables and fields can be returned.
New fields, including fields added to an already reviewed table, are hidden
until explicitly listed in the exposure policy.

Credential tables and unrestricted SQL queries are not exposed.

### Profile isolation

Every supported query is restricted to the configured
`ALLOS_PROFILE_ID`.

The profile ID is an administrative configuration value,
not a user credential.

### Authentication

HTTP requests must provide a valid Bearer token.

Tokens are read from a configured file and compared
using constant-time comparison.

A valid token authorizes access to the instance,
not to individual tools or data categories.

### Transport encryption

HTTP transport uses TLS.

The server can be configured directly with a certificate
and private key.

Clients must verify the certificate and ensure its
subjectAltName matches the destination.

### Automated tests

Regression tests cover:

- Read-only database behavior.
- Profile isolation.
- Table and field restrictions.
- Query validation.
- SQL injection resistance within supported interfaces.
- MCP protocol integration.
- Bearer-token authentication.
- HTTPS connectivity.
- Rejection of untrusted certificates.
- Rejection of plaintext HTTP.
- Rejection of missing security configuration.

Automated tests are not a formal security audit.

## Known Limitations

### Static Bearer tokens

The current HTTP authentication mechanism uses a
configured shared Bearer token.

It does not implement:

- OAuth authorization flows.
- Per-user identities.
- Per-client roles or permissions.
- Automatic token expiration.
- A token revocation API.
- Rate limiting.
- Comprehensive security audit logging.

Anyone possessing the valid token and able to connect
to the endpoint can potentially access the approved
health data for that instance.

To rotate the token, replace its secret file and
restart the MCP process or container.

### Direct database access

Allos MCP reads the SQLite database directly.

It does not use Allos' application-level authentication
or session authorization.

Database schema changes may affect compatibility.

A future upstream schema change could introduce additional
sensitive data requiring an allowlist review.

### Read-only does not guarantee confidentiality

Read-only database access prevents modification through MCP.

It does not prevent an authorized MCP client from
retrieving sensitive health records.

Clients and AI providers may process, retain or transmit
retrieved information according to their own policies.

Only connect MCP clients you trust.

### TLS protects transport, not endpoints

TLS protects information during network transmission.

It does not protect against:

- A compromised MCP client.
- A compromised server.
- Stolen Bearer tokens.
- Unauthorized filesystem access.
- An AI provider retaining supplied health information.

## Recommended Deployment

### Protect secrets

Store tokens and TLS private keys outside the source
repository and container image.

Use restricted filesystem permissions.

Do not include secrets in:

- Git commits.
- Container image layers.
- Command-line arguments.
- Logs.
- Screenshots.
- Public issue reports.

### Verify certificates

Use certificates with valid subjectAltName entries.

Use a certificate authority trusted by the MCP client
or explicitly configure the client to trust the intended
self-signed certificate.

Never disable TLS verification in production.

### Restrict network exposure

Bind the service only to the interfaces required
for the intended clients.

Use firewall restrictions where appropriate.

Bearer authentication is not a replacement for
network access controls.

### Protect the database

Mount the complete SQLite directory read-only.

Restrict access to the service account.

Avoid privileged containers.

Do not make medical data world-readable to work around
permission problems.

Keep backups protected.

### Keep dependencies updated

Apply security updates to the operating system,
Python runtime, MCP SDK and container image.

Review upstream dependency changes before deployment.

## Reporting a Vulnerability

Please do not publicly disclose an unpatched vulnerability
through a GitHub Issue, Discussion or Pull Request.

If private vulnerability reporting is enabled,
use GitHub's security advisory interface:

https://github.com/MVrauwdeunt/allos-mcp/security/advisories/new

If private reporting is unavailable, request a private
contact method without publishing exploit details.

When reporting an issue, include:

- A description of the vulnerability.
- The affected version.
- Relevant deployment information.
- Reproduction steps using synthetic data.
- Sanitized logs where necessary.

Never submit real medical records, credentials,
private keys or database backups.

## Disclosure and Response

Security reports are handled on a best-effort basis.

The maintainer will aim to review valid reports,
reproduce issues, develop fixes and publish advisories
when appropriate.

No guaranteed response or remediation timeline
is currently offered.

Coordinated disclosure is appreciated.

## Scope

This policy covers Allos MCP itself.

Issues in the upstream Allos application should be
reported through the upstream project's security process.

Allos MCP is an independent community project and is
not officially affiliated with or endorsed by Allos.

## License

The current development branch is licensed under
AGPL-3.0-only.

Earlier published versions may have different
license terms.

Refer to the LICENSE file in the relevant release.
```
