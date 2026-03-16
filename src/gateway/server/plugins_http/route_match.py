"""Plugin route matching — ported from openclaw server/plugins-http/route-match.ts.

Matches incoming HTTP paths against registered plugin routes
using exact or prefix matching.
"""
from __future__ import annotations

from typing import Any

from .path_context import (
    PluginRoutePathContext,
    canonicalize_path_variant,
    prefix_match_path,
    resolve_plugin_route_path_context,
)


def does_plugin_route_match_path(
    route: dict[str, Any],
    context: PluginRoutePathContext,
) -> bool:
    """Check if *route* matches any candidate in *context*.

    Routes with ``match='prefix'`` use prefix matching;
    everything else uses exact matching.
    """
    route_canonical = canonicalize_path_variant(route.get("path", ""))
    if route.get("match") == "prefix":
        return any(
            prefix_match_path(candidate, route_canonical)
            for candidate in context.candidates
        )
    return any(
        candidate == route_canonical for candidate in context.candidates
    )


def find_matching_plugin_http_routes(
    http_routes: list[dict[str, Any]],
    context: PluginRoutePathContext,
) -> list[dict[str, Any]]:
    """Return all routes that match *context*, sorted longest-path first.

    Exact matches come before prefix matches.
    """
    if not http_routes:
        return []

    exact: list[dict[str, Any]] = []
    prefix: list[dict[str, Any]] = []
    for route in http_routes:
        if not does_plugin_route_match_path(route, context):
            continue
        if route.get("match") == "prefix":
            prefix.append(route)
        else:
            exact.append(route)

    exact.sort(key=lambda r: len(r.get("path", "")), reverse=True)
    prefix.sort(key=lambda r: len(r.get("path", "")), reverse=True)
    return [*exact, *prefix]


def find_registered_plugin_http_route(
    http_routes: list[dict[str, Any]],
    pathname: str,
) -> dict[str, Any] | None:
    """Find the first route matching *pathname*."""
    context = resolve_plugin_route_path_context(pathname)
    matches = find_matching_plugin_http_routes(http_routes, context)
    return matches[0] if matches else None


def is_registered_plugin_http_route_path(
    http_routes: list[dict[str, Any]],
    pathname: str,
) -> bool:
    """Check if any registered route matches *pathname*."""
    return find_registered_plugin_http_route(http_routes, pathname) is not None
