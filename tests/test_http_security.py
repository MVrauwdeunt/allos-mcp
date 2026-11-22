
"""Check the command-line HTTP bind guard and local-only startup."""

import os
import socket
import subprocess
import sys
import time

import httpx


def _env(database):
    return {
        **os.environ,
        "ALLOS_DB_PATH": str(database),
        "ALLOS_PROFILE_ID": "1",
    }


def test_http_rejects_nonloopback_without_opt_in(sample_database):
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "allos_mcp",
            "--transport",
            "http",
            "--host",
            "0.0.0.0",
        ],
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


def test_http_accepts_loopback_and_initializes(sample_database):
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]

    process = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "allos_mcp",
            "--transport",
            "http",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
        ],
        env=_env(sample_database),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    try:
        url = f"http://127.0.0.1:{port}/mcp"
        deadline = time.monotonic() + 12

        while True:
            if process.poll() is not None:
                raise AssertionError(
                    "HTTP server exited before accepting connections"
                )

            try:
                response = httpx.post(
                    url,
                    headers={
                        "Content-Type": "application/json",
                        "Accept": "application/json, text/event-stream",
                    },
                    json={
                        "jsonrpc": "2.0",
                        "id": 1,
                        "method": "initialize",
                        "params": {
                            "protocolVersion": "2025-11-25",
                            "capabilities": {},
                            "clientInfo": {
                                "name": "pytest",
                                "version": "1.0",
                            },
                        },
                    },
                    timeout=2,
                )
                break

            except httpx.ConnectError:
                if time.monotonic() >= deadline:
                    raise AssertionError(
                        "HTTP server did not become ready"
                    )

                time.sleep(0.1)

        assert response.status_code == 200, response.text
        assert response.headers.get("mcp-session-id")

        assert (
            response.json()["result"]["serverInfo"]["name"]
            == "allos-mcp"
        )

    finally:
        process.terminate()

        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)
