"""Agent command handler.

Ported from bk/src/commands/agent.ts, agent-via-gateway.ts,
agents.ts, agents.commands.*.ts, agents.config.ts, agents.providers.ts,
agents.bindings.ts, agent-command-shared.ts.

Handles the `openclaw agent` command: run an agent with a message,
resolve agent identity, manage agent configurations.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class AgentCommandOptions:
    """Parsed options for the agent command."""
    message: str = ""
    agent_id: str | None = None
    model: str | None = None
    thinking: str | None = None
    session_key: str | None = None
    deliver: bool = False
    channel: str | None = None
    workspace_dir: str | None = None
    timeout: int | None = None
    verbose: bool = False
    json_output: bool = False
    resume: bool = False
    label: str | None = None
    system_prompt: str | None = None
    tools: list[str] | None = None
    attachments: list[str] | None = None


def parse_agent_options(args: list[str], options: dict[str, Any]) -> AgentCommandOptions:
    """Parse CLI args and options into AgentCommandOptions."""
    return AgentCommandOptions(
        message=" ".join(args) if args else "",
        agent_id=options.get("agent") or options.get("agentId"),
        model=options.get("model"),
        thinking=options.get("thinking"),
        session_key=options.get("session") or options.get("sessionKey"),
        deliver=bool(options.get("deliver", False)),
        channel=options.get("channel"),
        workspace_dir=options.get("workspaceDir") or options.get("cwd"),
        timeout=options.get("timeout"),
        verbose=bool(options.get("verbose", False)),
        json_output=bool(options.get("json", False)),
        resume=bool(options.get("resume", False)),
        label=options.get("label"),
        system_prompt=options.get("systemPrompt"),
        tools=options.get("tools"),
        attachments=options.get("attachments"),
    )


async def run_agent_command(
    opts: AgentCommandOptions,
    *,
    config: dict[str, Any] | None = None,
) -> int:
    """Execute the agent command.

    1. Resolve agent identity
    2. Build session key
    3. Connect to gateway (or run locally)
    4. Send message
    5. Stream response
    """
    if not opts.message and not opts.resume:
        logger.error("No message provided. Usage: openclaw agent 'your message'")
        return 1

    from ..config import load_config
    cfg = config or load_config()

    # Resolve agent
    agent_id = opts.agent_id or _resolve_default_agent(cfg)
    session_key = opts.session_key or "main"

    logger.info(f"Running agent={agent_id} session={session_key}")

    # Try gateway first
    gateway_mode = (cfg.get("gateway", {}) or {}).get("mode", "local")
    if gateway_mode == "local":
        return await _run_via_gateway(opts, cfg, agent_id, session_key)
    else:
        return await _run_locally(opts, cfg, agent_id, session_key)


def _resolve_default_agent(cfg: dict[str, Any]) -> str:
    """Resolve the default agent ID."""
    agents = cfg.get("agents", {}) or {}
    entries = agents.get("entries", {}) or {}
    if len(entries) == 1:
        return list(entries.keys())[0]
    return "default"


async def _run_via_gateway(
    opts: AgentCommandOptions,
    cfg: dict[str, Any],
    agent_id: str,
    session_key: str,
) -> int:
    """Run agent via gateway RPC."""
    import uuid

    gateway_cfg = cfg.get("gateway", {}) or {}
    port = gateway_cfg.get("port", 18789)
    host = "127.0.0.1"

    idempotency_key = str(uuid.uuid4())
    payload = {
        "method": "agent",
        "params": {
            "message": opts.message,
            "agentId": agent_id,
            "sessionKey": session_key,
            "idempotencyKey": idempotency_key,
            "deliver": opts.deliver,
        },
    }

    if opts.model:
        payload["params"]["model"] = opts.model
    if opts.thinking:
        payload["params"]["thinking"] = opts.thinking
    if opts.channel:
        payload["params"]["channel"] = opts.channel
    if opts.label:
        payload["params"]["label"] = opts.label
    if opts.system_prompt:
        payload["params"]["extraSystemPrompt"] = opts.system_prompt
    if opts.workspace_dir:
        payload["params"]["workspaceDir"] = opts.workspace_dir
    if opts.timeout:
        payload["params"]["timeout"] = opts.timeout

    try:
        import aiohttp
        url = f"http://{host}:{port}/rpc"
        auth_token = _resolve_gateway_token(cfg)
        headers = {"Content-Type": "application/json"}
        if auth_token:
            headers["Authorization"] = f"Bearer {auth_token}"

        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload, headers=headers) as resp:
                if resp.status != 200:
                    text = await resp.text()
                    logger.error(f"Gateway error ({resp.status}): {text}")
                    return 1
                result = await resp.json()
                if opts.json_output:
                    print(json.dumps(result, indent=2, ensure_ascii=False))
                else:
                    _print_agent_result(result)
                return 0
    except Exception as e:
        logger.error(f"Failed to connect to gateway: {e}")
        logger.info("Falling back to local execution...")
        return await _run_locally(opts, cfg, agent_id, session_key)


async def _run_locally(
    opts: AgentCommandOptions,
    cfg: dict[str, Any],
    agent_id: str,
    session_key: str,
) -> int:
    """Run agent locally (without gateway)."""
    logger.info(f"Running agent locally: {agent_id}")
    # Local execution would call directly into the agents module
    print(f"Agent '{agent_id}' response: [local execution not yet wired]")
    return 0


def _resolve_gateway_token(cfg: dict[str, Any]) -> str | None:
    """Resolve the gateway auth token."""
    env_token = os.environ.get("OPENCLAW_GATEWAY_TOKEN")
    if env_token:
        return env_token
    gateway = cfg.get("gateway", {}) or {}
    auth = gateway.get("auth", {}) or {}
    return auth.get("token")


def _print_agent_result(result: dict[str, Any]) -> None:
    """Pretty-print an agent result."""
    if result.get("ok") is False:
        error = result.get("error", {})
        msg = error.get("message", "Unknown error") if isinstance(error, dict) else str(error)
        print(f"Error: {msg}")
        return
    data = result.get("result", result.get("data", {}))
    if isinstance(data, dict):
        text = data.get("text") or data.get("summary") or data.get("message", "")
        if text:
            print(text)
    elif isinstance(data, str):
        print(data)


# ─── Agent management subcommands ───

async def list_agents(cfg: dict[str, Any], *, json_output: bool = False) -> int:
    """List configured agents."""
    agents = cfg.get("agents", {}) or {}
    entries = agents.get("entries", {}) or {}
    default_id = _resolve_default_agent(cfg)

    if json_output:
        print(json.dumps(list(entries.keys()), indent=2))
        return 0

    if not entries:
        print("No agents configured.")
        return 0

    print("Agents:")
    for agent_id, agent_cfg in sorted(entries.items()):
        marker = " (default)" if agent_id == default_id else ""
        model = ""
        if isinstance(agent_cfg, dict):
            model = str(agent_cfg.get("model", ""))
        print(f"  {agent_id}{marker}  model={model}")

    return 0


async def add_agent(
    agent_id: str,
    *,
    model: str = "",
    system_prompt: str = "",
    config: dict[str, Any] | None = None,
) -> int:
    """Add a new agent configuration."""
    from ..config import load_config, write_config_file
    from ..config.paths import resolve_config_path
    cfg = config or load_config()

    agents = cfg.get("agents", {}) or {}
    entries = agents.get("entries", {}) or {}
    if agent_id in entries:
        logger.error(f"Agent '{agent_id}' already exists")
        return 1

    entry: dict[str, Any] = {}
    if model:
        entry["model"] = model
    if system_prompt:
        entry["systemPrompt"] = system_prompt

    entries[agent_id] = entry
    agents["entries"] = entries
    cfg["agents"] = agents

    config_path = resolve_config_path()
    write_config_file(config_path, cfg)
    print(f"Agent '{agent_id}' added.")
    return 0


async def delete_agent(agent_id: str, *, config: dict[str, Any] | None = None) -> int:
    """Delete an agent configuration."""
    from ..config import load_config, write_config_file
    from ..config.paths import resolve_config_path
    cfg = config or load_config()

    agents = cfg.get("agents", {}) or {}
    entries = agents.get("entries", {}) or {}
    if agent_id not in entries:
        logger.error(f"Agent '{agent_id}' not found")
        return 1

    del entries[agent_id]
    agents["entries"] = entries
    cfg["agents"] = agents

    config_path = resolve_config_path()
    write_config_file(config_path, cfg)
    print(f"Agent '{agent_id}' deleted.")
    return 0
