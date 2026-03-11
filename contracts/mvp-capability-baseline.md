# Core Assistant Capability Baseline (v1)

The rewritten platform must preserve these capabilities:

- Chat run lifecycle: start, stream delta, final, error, abort.
- Session management: create, list, detail, message history.
- Tool orchestration: tool discovery, allowlist, lifecycle events.
- Memory: short-term session memory + long-term retrieval hooks.
- Model routing: primary/fallback provider policy.
- Operational guardrails: auth, rate limit, audit logs, observability hooks.
