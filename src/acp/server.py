"""ACP server — ported from bk/src/acp/server.ts.

ACP gateway server: loads config, connects to gateway, serves ACP over stdio.
"""
from __future__ import annotations

import sys
from typing import Any

from .secret_file import read_secret_from_file
from .types import AcpServerOptions


def parse_server_args(args: list[str]) -> AcpServerOptions:
    opts = AcpServerOptions()
    token_file: str | None = None
    password_file: str | None = None
    i = 0
    while i < len(args):
        arg = args[i]
        if arg in ("--url", "--gateway-url") and i + 1 < len(args):
            opts.gateway_url = args[i + 1]; i += 2; continue
        if arg in ("--token", "--gateway-token") and i + 1 < len(args):
            opts.gateway_token = args[i + 1]; i += 2; continue
        if arg in ("--token-file", "--gateway-token-file") and i + 1 < len(args):
            token_file = args[i + 1]; i += 2; continue
        if arg in ("--password", "--gateway-password") and i + 1 < len(args):
            opts.gateway_password = args[i + 1]; i += 2; continue
        if arg in ("--password-file", "--gateway-password-file") and i + 1 < len(args):
            password_file = args[i + 1]; i += 2; continue
        if arg == "--session" and i + 1 < len(args):
            opts.default_session_key = args[i + 1]; i += 2; continue
        if arg == "--session-label" and i + 1 < len(args):
            opts.default_session_label = args[i + 1]; i += 2; continue
        if arg == "--require-existing":
            opts.require_existing_session = True; i += 1; continue
        if arg == "--reset-session":
            opts.reset_session = True; i += 1; continue
        if arg == "--no-prefix-cwd":
            opts.prefix_cwd = False; i += 1; continue
        if arg in ("--verbose", "-v"):
            opts.verbose = True; i += 1; continue
        if arg in ("--help", "-h"):
            _print_help(); sys.exit(0)
        i += 1

    if opts.gateway_token and token_file:
        raise ValueError("Use either --token or --token-file.")
    if opts.gateway_password and password_file:
        raise ValueError("Use either --password or --password-file.")
    if token_file:
        opts.gateway_token = read_secret_from_file(token_file, "Gateway token")
    if password_file:
        opts.gateway_password = read_secret_from_file(password_file, "Gateway password")
    return opts


def _print_help() -> None:
    print("""Usage: openclaw acp [options]

Gateway-backed ACP server for IDE integration.

Options:
  --url <url>             Gateway WebSocket URL
  --token <token>         Gateway auth token
  --token-file <path>     Read gateway auth token from file
  --password <password>   Gateway auth password
  --password-file <path>  Read gateway auth password from file
  --session <key>         Default session key
  --session-label <label> Default session label to resolve
  --require-existing      Fail if the session key/label does not exist
  --reset-session         Reset the session key before first use
  --no-prefix-cwd         Do not prefix prompts with the working directory
  --verbose, -v           Verbose logging to stderr
  --help, -h              Show this help message
""")


async def serve_acp_gateway(opts: AcpServerOptions | None = None) -> None:
    """Start ACP gateway server (placeholder — real impl connects websocket)."""
    pass
