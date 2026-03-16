"""WebSocket connection handling — corresponds to openclaw's server/ws-connection/.

Contains the core message handler that processes all gateway RPC methods
over the WebSocket connection, auth helpers, connect policy, and flood guard.

Modules:
    message_handler     — main WebSocket message handler (RPC dispatch)
    protocol            — WebSocket protocol helpers
    auth_context        — connect auth state resolution
    auth_messages       — human-readable auth failure messages
    connect_policy      — Control UI auth policy, device identity evaluation
    handshake_auth_helpers — browser security, silent pairing, signature
    unauthorized_flood_guard — flood protection for unauthorized requests
"""
