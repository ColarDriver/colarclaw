"""Auth profile doctor — ported from bk/src/agents/auth-profiles/doctor.ts.

Diagnostic checks for auth profile configuration.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .credential_state import evaluate_stored_credential_eligibility
from .types import AuthProfileStore


@dataclass
class AuthDiagnosticResult:
    profile_id: str
    provider: str
    type: str
    eligible: bool
    reason_code: str
    has_expiry: bool = False
    is_expired: bool = False
    email: str | None = None


@dataclass
class AuthDoctorReport:
    total_profiles: int = 0
    eligible_profiles: int = 0
    ineligible_profiles: int = 0
    results: list[AuthDiagnosticResult] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def run_auth_doctor(store: AuthProfileStore) -> AuthDoctorReport:
    """Run diagnostic checks on auth profiles."""
    report = AuthDoctorReport(total_profiles=len(store.profiles))

    for pid, cred in store.profiles.items():
        eligibility = evaluate_stored_credential_eligibility(cred)
        result = AuthDiagnosticResult(
            profile_id=pid,
            provider=getattr(cred, "provider", "unknown"),
            type=getattr(cred, "type", "unknown"),
            eligible=eligibility["eligible"],
            reason_code=eligibility["reason_code"],
            email=getattr(cred, "email", None),
        )
        if hasattr(cred, "expires") and cred.expires:
            result.has_expiry = True
            result.is_expired = eligibility["reason_code"] == "expired"

        report.results.append(result)
        if result.eligible:
            report.eligible_profiles += 1
        else:
            report.ineligible_profiles += 1

    if report.eligible_profiles == 0 and report.total_profiles > 0:
        report.warnings.append("No eligible auth profiles found")

    return report
