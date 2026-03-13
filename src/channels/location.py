"""Channels location — ported from bk/src/channels/location.ts.

Normalized location types and formatting.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Literal


LocationSource = Literal["pin", "place", "live"]


@dataclass
class NormalizedLocation:
    latitude: float = 0.0
    longitude: float = 0.0
    accuracy: float | None = None
    name: str | None = None
    address: str | None = None
    is_live: bool = False
    source: LocationSource | None = None
    caption: str | None = None


def _resolve_location(loc: NormalizedLocation) -> NormalizedLocation:
    """Resolve source and is_live from available info."""
    source = loc.source
    if not source:
        if loc.is_live:
            source = "live"
        elif loc.name or loc.address:
            source = "place"
        else:
            source = "pin"
    is_live = loc.is_live or source == "live"
    return NormalizedLocation(
        latitude=loc.latitude, longitude=loc.longitude,
        accuracy=loc.accuracy, name=loc.name, address=loc.address,
        is_live=is_live, source=source, caption=loc.caption,
    )


def _format_accuracy(accuracy: float | None) -> str:
    if accuracy is None or not math.isfinite(accuracy):
        return ""
    return f" ±{round(accuracy)}m"


def _format_coords(lat: float, lon: float) -> str:
    return f"{lat:.6f}, {lon:.6f}"


def format_location_text(location: NormalizedLocation) -> str:
    """Format a location into human-readable text."""
    resolved = _resolve_location(location)
    coords = _format_coords(resolved.latitude, resolved.longitude)
    accuracy = _format_accuracy(resolved.accuracy)
    caption = (resolved.caption or "").strip()

    if resolved.source == "live" or resolved.is_live:
        header = f"🛰 Live location: {coords}{accuracy}"
    elif resolved.name or resolved.address:
        label = " — ".join(s for s in (resolved.name, resolved.address) if s)
        header = f"📍 {label} ({coords}{accuracy})"
    else:
        header = f"📍 {coords}{accuracy}"

    return f"{header}\n{caption}" if caption else header


def to_location_context(location: NormalizedLocation) -> dict:
    """Convert a NormalizedLocation to a context dict."""
    resolved = _resolve_location(location)
    result = {
        "LocationLat": resolved.latitude,
        "LocationLon": resolved.longitude,
        "LocationSource": resolved.source,
        "LocationIsLive": resolved.is_live,
    }
    if resolved.accuracy is not None:
        result["LocationAccuracy"] = resolved.accuracy
    if resolved.name:
        result["LocationName"] = resolved.name
    if resolved.address:
        result["LocationAddress"] = resolved.address
    return result
