# Migration Checklist (Big Bang)

## Pre-cut

- Freeze legacy writes during maintenance window.
- Export legacy sessions snapshot.
- Run `scripts/migrate_sessions.py`.
- Run `scripts/validate_migration.py`.
- Run smoke tests against Python API and React frontend.

## Cutover

- Deploy backend stack (api, postgres, redis, vector store).
- Deploy frontend static bundle.
- Switch ingress routing and DNS.
- Monitor P95 latency and error rate for 60 minutes.

## Post-cut

- Validate session list and sample chat history.
- Validate tool call traces and audit logs.
- Keep rollback artifacts for at least 7 days.
