"""Plugin HTTP routing — corresponds to openclaw's server/plugins-http/.

Handles HTTP route matching, path canonicalization, and auth enforcement
for plugin-registered HTTP endpoints.

Modules:
    path_context — URL path canonicalization and security checks
    route_match  — plugin HTTP route matching (exact + prefix)
    route_auth   — gateway auth enforcement for plugin routes
"""
