# Rollback Runbook

## Triggers

- Sustained 5xx > threshold for 10 minutes.
- Critical chat run failures with no workaround.
- Data integrity mismatch discovered after cutover.

## Rollback Steps

1. Re-point ingress/DNS to legacy stack.
2. Re-enable legacy write path.
3. Capture failed runs for post-mortem.
4. Notify users of rollback completion.

## Recovery

- Root-cause analysis.
- Patch candidate environment.
- Re-run shadow validation before next cutover.
