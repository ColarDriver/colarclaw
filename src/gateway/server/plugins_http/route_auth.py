"""Plugin route auth — ported from openclaw server/plugins-http/route-auth.ts.

Determines whether a given plugin HTTP path requires gateway authentication.
"""
from __future__ import annotations

from typing import Any

from .path_context import (
    PluginRoutePathContext,
    is_protected_plugin_route_path_from_context,
    resolve_plugin_route_path_context,
)
from .route_match import find_matching_plugin_http_routes


def matched_plugin_routes_require_gateway_auth(
    routes: list[dict[str, Any]],
) -> bool:
    """Return ``True`` if any *route* requires ``gateway`` auth."""
    return any(route.get("auth") == "gateway" for route in routes)


def should_enforce_gateway_auth_for_plugin_path(
    http_routes: list[dict[str, Any]],
    pathname_or_context: str | PluginRoutePathContext,
) -> bool:
    """Port of OpenClaw's ``shouldEnforceGatewayAuthForPluginPath``.

    Returns ``True`` when gateway auth must be enforced for the given path.
    """
    if isinstance(pathname_or_context, str):
        context = resolve_plugin_route_path_context(pathname_or_context)
    else:
        context = pathname_or_context

    if context.malformed_encoding or context.decode_pass_limit_reached:
        return True
    if is_protected_plugin_route_path_from_context(context):
        return True
    return matched_plugin_routes_require_gateway_auth(
        find_matching_plugin_http_routes(http_routes, context),
    )
