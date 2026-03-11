# Big Bang Cutover Runbook

## 1. Freeze

1. Announce maintenance window.
2. Disable write traffic to legacy runtime.
3. Capture final data export.

## 2. Migrate

1. Transform historical sessions using migration script.
2. Import transformed dataset into new backend repository.
3. Validate cardinality and random spot checks.

## 3. Switch

1. Roll out backend deployment.
2. Roll out frontend deployment.
3. Flip DNS/ingress target to new stack.

## 4. Verify

1. Health checks: `/healthz`, `/v1/sessions`, `/v1/tools`.
2. WebSocket smoke: `chat.send -> delta -> final`.
3. Observe error budget for 24h.
