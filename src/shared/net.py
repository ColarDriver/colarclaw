"""Shared IP address handling — ported from bk/src/shared/net/ip.ts, net/ipv4.ts.

IP address parsing, classification, CIDR matching, and special-use range detection.
Uses Python's ipaddress stdlib module.
"""
from __future__ import annotations

import ipaddress
import re
from typing import Any


# ─── classification sets ───

_BLOCKED_IPV4_RANGES = {
    "UNSPECIFIED", "RESERVED", "PRIVATE", "LOOPBACK",
    "LINK_LOCAL", "MULTICAST",
}

_PRIVATE_OR_LOOPBACK_IPV4 = {"LOOPBACK", "PRIVATE", "LINK_LOCAL"}


def _classify_ipv4(addr: ipaddress.IPv4Address) -> str:
    """Classify an IPv4 address into a range category."""
    if addr.is_unspecified:
        return "UNSPECIFIED"
    if addr.is_loopback:
        return "LOOPBACK"
    if addr.is_private:
        return "PRIVATE"
    if addr.is_link_local:
        return "LINK_LOCAL"
    if addr.is_multicast:
        return "MULTICAST"
    if addr.is_reserved:
        return "RESERVED"
    # Carrier-grade NAT: 100.64.0.0/10
    if addr in ipaddress.IPv4Network("100.64.0.0/10"):
        return "CARRIER_GRADE_NAT"
    return "PUBLIC"


def _classify_ipv6(addr: ipaddress.IPv6Address) -> str:
    if addr.is_unspecified:
        return "UNSPECIFIED"
    if addr.is_loopback:
        return "LOOPBACK"
    if addr.is_link_local:
        return "LINK_LOCAL"
    if addr.is_private:
        return "UNIQUE_LOCAL"
    if addr.is_multicast:
        return "MULTICAST"
    return "GLOBAL"


# ─── parsing ───

def _strip_brackets(value: str) -> str:
    if value.startswith("[") and value.endswith("]"):
        return value[1:-1]
    return value


def parse_canonical_ip_address(raw: str | None) -> ipaddress.IPv4Address | ipaddress.IPv6Address | None:
    """Parse an IP address string into an IPv4 or IPv6 address object."""
    trimmed = (raw or "").strip()
    if not trimmed:
        return None
    normalized = _strip_brackets(trimmed)
    if not normalized:
        return None
    # Strip zone ID for IPv6
    if "%" in normalized:
        normalized = normalized.split("%")[0]
    try:
        addr = ipaddress.ip_address(normalized)
        # For IPv6-mapped IPv4, extract the IPv4 part
        if isinstance(addr, ipaddress.IPv6Address) and addr.ipv4_mapped:
            return addr.ipv4_mapped
        return addr
    except ValueError:
        return None


def normalize_ip_address(raw: str | None) -> str | None:
    """Normalize an IP address string."""
    parsed = parse_canonical_ip_address(raw)
    if not parsed:
        return None
    return str(parsed).lower()


def is_loopback_ip_address(raw: str | None) -> bool:
    parsed = parse_canonical_ip_address(raw)
    return parsed.is_loopback if parsed else False


def is_private_or_loopback_ip_address(raw: str | None) -> bool:
    parsed = parse_canonical_ip_address(raw)
    if not parsed:
        return False
    if isinstance(parsed, ipaddress.IPv4Address):
        return parsed.is_loopback or parsed.is_private or parsed.is_link_local
    return parsed.is_loopback or parsed.is_private or parsed.is_link_local


def is_rfc1918_ipv4_address(raw: str | None) -> bool:
    parsed = parse_canonical_ip_address(raw)
    if not parsed or not isinstance(parsed, ipaddress.IPv4Address):
        return False
    return parsed.is_private


def is_carrier_grade_nat_ipv4_address(raw: str | None) -> bool:
    parsed = parse_canonical_ip_address(raw)
    if not parsed or not isinstance(parsed, ipaddress.IPv4Address):
        return False
    return parsed in ipaddress.IPv4Network("100.64.0.0/10")


# ─── CIDR matching ───

def is_ip_in_cidr(ip: str, cidr: str) -> bool:
    """Check if an IP address is within a CIDR range."""
    parsed_ip = parse_canonical_ip_address(ip)
    if not parsed_ip:
        return False
    candidate = cidr.strip()
    if not candidate:
        return False

    if "/" not in candidate:
        # Exact match
        exact = parse_canonical_ip_address(candidate)
        if not exact:
            return False
        return parsed_ip == exact

    try:
        network = ipaddress.ip_network(candidate, strict=False)
        return parsed_ip in network
    except ValueError:
        return False


# ─── ipv4.ts ───

_FOUR_PART_DECIMAL_RE = re.compile(
    r"^(\d{1,3})\.(\d{1,3})\.(\d{1,3})\.(\d{1,3})$"
)


def is_canonical_dotted_decimal_ipv4(raw: str | None) -> bool:
    trimmed = (raw or "").strip()
    if not trimmed:
        return False
    normalized = _strip_brackets(trimmed)
    if not normalized:
        return False
    m = _FOUR_PART_DECIMAL_RE.match(normalized)
    if not m:
        return False
    try:
        parts = [int(g) for g in m.groups()]
        return all(0 <= p <= 255 for p in parts)
    except ValueError:
        return False
