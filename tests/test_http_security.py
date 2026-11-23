
"""Security and integration tests for the HTTPS MCP transport."""

import asyncio
import os
import shutil
import socket
import ssl
import subprocess
import sys
import time

from importlib.metadata import version

import httpx
import pytest

from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client


SECURITY_ENV_VARS = (
    "ALLOS_MCP_AUTH_TOKEN_FILE",
    "ALLOS_MCP_TLS_CERT_FILE",
    "ALLOS_MCP_TLS_KEY_FILE",
)


def _env(database):
    """Build a predictable environment for subprocess tests."""
    env = {
        **os.environ,
        "ALLOS_DB_PATH": str(database),
        "ALLOS_PROFILE_ID": "1",
    }

    for name in SECURITY_ENV_VARS:
        env.pop(name, None)

    return env


def _free_port():
    """Find an available local TCP port."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _command(port, host="127.0.0.1"):
    """Build the Allos MCP HTTP startup command."""
    return [
        sys.executable,
        "-m",
        "allos_mcp",
        "--transport",
        "http",
        "--host",
        host,
        "--port",
        str(port),
    ]


@pytest.fixture
def http_secrets(tmp_path):
    """Generate isolated test credentials and a TLS certificate."""
    if shutil.which("openssl") is None:
        pytest.fail("OpenSSL is required for HTTP security tests")

    secrets = tmp_path / "secrets"
    secrets.mkdir(mode=0o700)

    token_file = secrets / "token"
    cert_file = secrets / "server.crt"
    key_file = secrets / "server.key"

    # Generate a cryptographically random 256-bit token.
    token = os.urandom(32).hex()
    token_file.write_text(token + "\n", encoding="ascii")
    token_file.chmod(0o600)

    # Generate a short-lived certificate for local integration tests.
    subprocess.run(
        [
            "openssl",
            "req",
            "-x509",
            "-newkey",
            "rsa:2048",
            "-sha256",
            "-nodes",
            "-days",
            "1",
            "-keyout",
            str(key_file),
            "-out",
            str(cert_file),
            "-subj",
            "/CN=localhost",
            "-addext",
            "subjectAltName=DNS:localhost,IP:127.0.0.1",
        ],
        check=True,
        capture_output=True,
        text=True,
        timeout=20,
    )

    key_file.chmod(0o600)

    return {
        "token": token,
        "token_file": token_file,
        "cert_file": cert_file,
        "key_file": key_file,
    }


@pytest.fixture
def secure_http_server(sample_database, http_secrets):
    """Start Allos MCP with HTTPS and Bearer authentication."""
    port = _free_port()

    env = _env(sample_database)
    env.update(
        {
            "ALLOS_MCP_AUTH_TOKEN_FILE": str(
                http_secrets["token_file"]
            ),
            "ALLOS_MCP_TLS_CERT_FILE": str(
                http_secrets["cert_file"]
            ),
            "ALLOS_MCP_TLS_KEY_FILE": str(
                http_secrets["key_file"]
            ),
        }
    )

    process = subprocess.Popen(
        _command(port),
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        text=True,
    )

    url = f"https://127.0.0.1:{port}/mcp"
    deadline = time.monotonic() + 12

    try:
        # Check TCP readiness without disabling TLS verification.
        while True:
            if process.poll() is not None:
                stderr = process.stderr.read()
                raise AssertionError(
                    "HTTPS server exited during startup:\n"
                    + stderr
                )

            try:
                with socket.create_connection(
                    ("127.0.0.1", port),
                    timeout=0.5,
                ):
                    break
            except (OSError, TimeoutError):
                if time.monotonic() >= deadline:
                    raise AssertionError(
                        "HTTPS server did not become ready"
                    )

                time.sleep(0.1)

        yield {
            "url": url,
            "port": port,
            "token": http_secrets["token"],
            "cert_file": http_secrets["cert_file"],
            "process": process,
        }

    finally:
        if process.poll() is None:
            process.terminate()

            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)

        if process.stderr is not None:
            process.stderr.close()


def test_http_rejects_nonloopback_without_opt_in(sample_database):
    """Non-loopback binding must require explicit authorization."""
    result = subprocess.run(
        _command(_free_port(), host="0.0.0.0"),
        env=_env(sample_database),
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )

    assert result.returncode != 0
    assert (
        "Non-loopback HTTP requires --allow-nonloopback"
        in result.stderr
    )


def test_http_requires_security_configuration(sample_database):
    """HTTP must fail closed when authentication or TLS is missing."""
    result = subprocess.run(
        _command(_free_port()),
        env=_env(sample_database),
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )

    assert result.returncode != 0
    assert "ALLOS_MCP_AUTH_TOKEN_FILE" in result.stderr
    assert "ALLOS_MCP_TLS_CERT_FILE" in result.stderr
    assert "ALLOS_MCP_TLS_KEY_FILE" in result.stderr


def test_http_rejects_missing_and_invalid_tokens(secure_http_server):
    """Unauthenticated clients must never reach MCP."""
    url = secure_http_server["url"]
    cert = str(secure_http_server["cert_file"])

    tls_context = ssl.create_default_context(cafile=cert)

    with httpx.Client(
        verify=tls_context,
        timeout=5,
    ) as client:
        # No Authorization header.
        response = client.get(url)

        assert response.status_code == 401
        assert response.json() == {
            "error": "unauthorized"
        }
        assert response.headers["www-authenticate"] == "Bearer"
        assert response.headers["cache-control"] == "no-store"

        # Incorrect Bearer token.
        response = client.get(
            url,
            headers={
                "Authorization": "Bearer wrong-token",
            },
        )

        assert response.status_code == 401

        # Reject another authentication scheme.
        response = client.get(
            url,
            headers={
                "Authorization": "Basic invalid",
            },
        )

        assert response.status_code == 401

        # Reject duplicate Authorization headers.
        response = client.get(
            url,
            headers=[
                (
                    "Authorization",
                    f"Bearer {secure_http_server['token']}",
                ),
                (
                    "Authorization",
                    "Bearer wrong-token",
                ),
            ],
        )

        assert response.status_code == 401


def test_http_accepts_valid_token(secure_http_server):
    """A valid token must reach the MCP protocol handler."""
    url = secure_http_server["url"]
    cert = str(secure_http_server["cert_file"])
    token = secure_http_server["token"]

    tls_context = ssl.create_default_context(cafile=cert)

    with httpx.Client(
        verify=tls_context,
        timeout=5,
    ) as client:
        # A GET without the required Accept header is rejected
        # by MCP, not by the authentication middleware.
        response = client.get(
            url,
            headers={
                "Authorization": f"Bearer {token}",
            },
        )

    assert response.status_code == 406
    assert response.status_code != 401


def test_https_rejects_untrusted_certificate(secure_http_server):
    """A client must reject an untrusted self-signed certificate."""
    with pytest.raises(httpx.ConnectError):
        httpx.get(
            secure_http_server["url"],
            headers={
                "Authorization": (
                    f"Bearer {secure_http_server['token']}"
                ),
            },
            timeout=5,
            trust_env=False,
        )


def test_plain_http_is_not_accepted(secure_http_server):
    """The HTTPS-only endpoint must not accept plaintext HTTP."""
    url = secure_http_server["url"].replace(
        "https://",
        "http://",
        1,
    )

    with pytest.raises(httpx.TransportError):
        httpx.get(
            url,
            timeout=5,
            trust_env=False,
        )


def test_https_mcp_client_initializes_and_calls_tool(
    secure_http_server,
):
    """Verify a real authenticated MCP session over HTTPS."""
    url = secure_http_server["url"]
    cert = str(secure_http_server["cert_file"])
    token = secure_http_server["token"]

    async def run_client():
        tls_context = ssl.create_default_context(cafile=cert)

        async with httpx.AsyncClient(
            verify=tls_context,
            headers={
                "Authorization": f"Bearer {token}",
            },
            timeout=30.0,
        ) as http_client:
            async with streamable_http_client(
                url,
                http_client=http_client,
            ) as (read, write, _):
                async with ClientSession(read, write) as session:
                    initialized = await session.initialize()

                    assert initialized.serverInfo.name == "allos-mcp"
                    assert (
                        initialized.serverInfo.version
                        == version("allos-mcp")
                    )

                    tools = await session.list_tools()

                    tool_names = {
                        tool.name
                        for tool in tools.tools
                    }

                    assert tool_names == {
                        "allos_catalog",
                        "allos_metrics",
                        "allos_read",
                        "allos_metric_trend",
                    }

                    # Execute a real tool, not just discovery.
                    result = await session.call_tool(
                        "allos_catalog",
                        {},
                    )

                    assert not result.isError

                    if result.structuredContent is not None:
                        data = result.structuredContent
                    else:
                        data = [
                            part.text
                            for part in result.content
                            if part.type == "text"
                        ]

                    assert data

    asyncio.run(run_client())
