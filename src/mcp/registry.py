from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class McpServerConfig:
    name: str
    command: str
    enabled: bool = True


class McpRegistry:
    def __init__(self, servers: list[McpServerConfig] | None = None) -> None:
        self._servers: dict[str, McpServerConfig] = {}
        if servers:
            self.replace(servers)

    def replace(self, servers: list[McpServerConfig]) -> None:
        parsed: dict[str, McpServerConfig] = {}
        for server in servers:
            name = server.name.strip()
            command = server.command.strip()
            if not name or not command:
                continue
            parsed[name] = McpServerConfig(name=name, command=command, enabled=bool(server.enabled))
        self._servers = parsed

    def list(self) -> list[McpServerConfig]:
        return sorted(self._servers.values(), key=lambda item: item.name)


def parse_mcp_servers(raw_entries: tuple[str, ...]) -> list[McpServerConfig]:
    parsed: list[McpServerConfig] = []
    for raw in raw_entries:
        value = raw.strip()
        if not value:
            continue
        if "=" not in value:
            continue
        name, command = value.split("=", 1)
        name = name.strip()
        command = command.strip()
        if not name or not command:
            continue
        parsed.append(McpServerConfig(name=name, command=command, enabled=True))
    return parsed
