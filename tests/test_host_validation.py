import os
import subprocess
import sys


def test_remote_host_allowlist():
    env = os.environ.copy()
    env["ALLOS_MCP_ALLOWED_HOSTS"] = "mcp.example.com:8765"

    subprocess.run(
        [
            sys.executable,
            "-c",
            """
from allos_mcp.server import mcp

security = mcp.settings.transport_security

assert security.enable_dns_rebinding_protection is True
assert "mcp.example.com:8765" in security.allowed_hosts
assert "localhost:*" in security.allowed_hosts
assert "*" not in security.allowed_hosts
assert "untrusted.example.com:8765" not in security.allowed_hosts
""",
        ],
        env=env,
        check=True,
    )


def test_default_host_allowlist():
    env = os.environ.copy()
    env.pop("ALLOS_MCP_ALLOWED_HOSTS", None)

    subprocess.run(
        [
            sys.executable,
            "-c",
            """
from allos_mcp.server import mcp

security = mcp.settings.transport_security

assert security.enable_dns_rebinding_protection is True
assert "localhost:*" in security.allowed_hosts
assert "127.0.0.1:*" in security.allowed_hosts
assert "mcp.example.com:8765" not in security.allowed_hosts
""",
        ],
        env=env,
        check=True,
    )
