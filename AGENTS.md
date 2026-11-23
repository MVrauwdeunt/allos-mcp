
# AGENTS.md

## Project

Allos MCP is an independent, experimental, read-only MCP
server for the self-hosted Allos personal health application.

It exposes selected structured health measurements through
the Model Context Protocol.

The project uses Python, the official MCP Python SDK,
SQLite, and optionally Streamable HTTP over HTTPS.

## Repository structure

- `src/allos_mcp/server.py`: MCP tools, transports, authentication
  and HTTPS startup.
- `src/allos_mcp/db.py`: SQLite access, query restrictions,
  profile isolation and metric aggregation.
- `tests/`: Automated unit, security and integration tests.
- `examples/compose.yaml`: Container deployment example.
- `Containerfile`: OCI container image.
- `README.md`: Installation, configuration and usage.
- `SECURITY.md`: Security policy and vulnerability reporting.
- `.github/workflows/`: CI and container publishing.

## Non-negotiable security requirements

1. Never implement database writes through MCP.
2. Never introduce arbitrary client-supplied SQL.
3. Preserve explicit table and column restrictions.
4. Enforce `ALLOS_PROFILE_ID` for every profile-scoped query.
5. Never expose authentication tables, credentials or secrets.
6. Never log Bearer tokens, TLS private keys or health records.
7. Never disable TLS certificate verification in production.
8. Require Bearer authentication and TLS for HTTP transport.
9. Keep STDIO independent of HTTP authentication.
10. Do not bypass database authorization after an API failure.

## HTTP transport

- The MCP HTTP endpoint uses Streamable HTTP.
- TLS is terminated directly by the Python/Uvicorn server.
- Authentication is performed before MCP request handling.
- Every HTTP request requires a valid Bearer token.
- Tokens must be loaded from secret files.
- TLS certificates and private keys are configured through
  environment variables pointing to files.
- Missing security configuration must prevent HTTP startup.
- Do not introduce reverse proxies, VPNs, OAuth services
  or other infrastructure without an explicit requirement.

## Database access

- SQLite connections must remain read-only.
- Prefer `mode=ro` and `PRAGMA query_only=ON`.
- Never modify the Allos database schema.
- Never assume new upstream columns are safe to expose.
- Only reviewed health tables and fields may be returned.
- Profile isolation must be covered by regression tests.

## Compatibility

Maintain the existing MCP tools:

- `allos_catalog`
- `allos_metrics`
- `allos_read`
- `allos_metric_trend`

Avoid changing tool names, parameters or response formats
without an explicit compatibility plan.

## Testing

Install development dependencies:

```bash
python -m pip install -e '.[test]'
```

Run the complete suite:

```bash
python -m pytest -q
```

Validate Python syntax:

```bash
python -m compileall -q src/allos_mcp
```

Use synthetic databases in tests.

Never require real medical records, production credentials
or production certificates to execute CI tests.

Every authentication or transport change must include tests
covering successful and rejected connections.

## Documentation

Update README.md and SECURITY.md when security behavior changes.

Keep examples consistent with the actual implementation.

Never document insecure HTTP as an acceptable production
configuration.

## Releases

Forgejo is the primary Git repository.

GitHub is a mirror used for public distribution,
GitHub Actions and GHCR publishing.

Do not create release tags before the complete CI suite passes.

## Coding conventions

- Use English for code comments and docstrings.
- Prefer standard-library functionality where appropriate.
- Keep dependencies minimal.
- Use clear errors for invalid configuration.
- Do not silently weaken security to preserve compatibility.
- Avoid unrelated refactoring in security changes.
```
