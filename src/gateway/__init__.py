"""Gateway package — ported from bk/src/gateway/.

The gateway is the core HTTP/WebSocket server that orchestrates
all communication between channels, agents, sessions, and LLM providers.

Sub-packages:
    protocol/  — wire protocol schema, frame types, client info
    methods/   — RPC method handlers (agent, chat, sessions, etc.)

Modules (root):
    types          — core gateway types and enums
    events         — gateway event system
    auth           — authentication, rate limiting, credentials
    net            — network binding, URL resolution
    call           — gateway API call orchestration
    client         — WebSocket gateway client
    credentials    — credential resolution
    chat           — chat abort, attachments, sanitization
    control_ui     — control plane UI routing, CSP, shared
    hooks          — hook mapping and execution
    channel_health — channel health monitoring and policy
    session_utils  — session management, patching, listing
    config_reload  — hot config reload and runtime config
    server_runtime — server state, broadcast, dedupe, close handler
    server_http    — HTTP server, OpenAI compat, plugin routes
    server_impl    — main server class, boot, maintenance, plugins
    ws_connection  — WS lifecycle, auth, message dispatch, health
    ws_log         — WS message logging (compact/verbose/optimized)
    security       — auth policies, rate limiting, origin checks
    nodes          — node registry, command policy, exec approval
    exec_approvals — exec approval manager
    cron           — cron scheduling and execution
"""
