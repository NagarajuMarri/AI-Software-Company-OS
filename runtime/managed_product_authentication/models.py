"""Immutable authentication persistence and security verification authority."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
from enum import Enum
import hashlib
import json
import re

from runtime.runtime_acceptance.models import EvidenceKind
from runtime.runtime_acceptance.profiles import AUTHENTICATION_JOURNEYS


_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")
_DIGEST = re.compile(r"^[0-9a-f]{64}$")
_SHA = re.compile(r"^[0-9a-f]{40}$")


class AuthenticationClaim(str, Enum):
    REGISTRATION_PERSISTED = "REGISTRATION_PERSISTED"
    DUPLICATE_REJECTED = "DUPLICATE_REJECTED"
    LOGIN_SUCCEEDED = "LOGIN_SUCCEEDED"
    LOGOUT_REVOKED = "LOGOUT_REVOKED"
    SESSION_RESTORED = "SESSION_RESTORED"
    PASSWORD_CHANGED = "PASSWORD_CHANGED"
    OLD_PASSWORD_REJECTED = "OLD_PASSWORD_REJECTED"
    RESET_SINGLE_USE = "RESET_SINGLE_USE"
    UNKNOWN_EMAIL_PRIVATE = "UNKNOWN_EMAIL_PRIVATE"
    INVALID_TOKEN_REJECTED = "INVALID_TOKEN_REJECTED"
    PARTIAL_FAILURE_ATOMIC = "PARTIAL_FAILURE_ATOMIC"
    THROTTLED = "THROTTLED"
    PASSWORD_STORAGE_HARDENED = "PASSWORD_STORAGE_HARDENED"
    TOKEN_STORAGE_HARDENED = "TOKEN_STORAGE_HARDENED"


LOCKED_AUTHENTICATION_CLAIMS = {
    "authentication.registration": (
        AuthenticationClaim.REGISTRATION_PERSISTED,
        AuthenticationClaim.PASSWORD_STORAGE_HARDENED,
        AuthenticationClaim.TOKEN_STORAGE_HARDENED,
    ),
    "authentication.login": (AuthenticationClaim.LOGIN_SUCCEEDED,),
    "authentication.logout": (
        AuthenticationClaim.LOGOUT_REVOKED,
        AuthenticationClaim.TOKEN_STORAGE_HARDENED,
    ),
    "authentication.session_restore": (AuthenticationClaim.SESSION_RESTORED,),
    "authentication.password_recovery": (
        AuthenticationClaim.PASSWORD_CHANGED,
        AuthenticationClaim.OLD_PASSWORD_REJECTED,
        AuthenticationClaim.RESET_SINGLE_USE,
    ),
    "authentication.security_error_paths": (
        AuthenticationClaim.DUPLICATE_REJECTED,
        AuthenticationClaim.UNKNOWN_EMAIL_PRIVATE,
        AuthenticationClaim.INVALID_TOKEN_REJECTED,
        AuthenticationClaim.PARTIAL_FAILURE_ATOMIC,
        AuthenticationClaim.THROTTLED,
    ),
}

_LOCKED_EVIDENCE_KINDS = {
    "authentication.registration": (EvidenceKind.PERSISTENCE, EvidenceKind.SECURITY),
    "authentication.login": (EvidenceKind.SECURITY,),
    "authentication.logout": (EvidenceKind.PERSISTENCE, EvidenceKind.SECURITY),
    "authentication.session_restore": (EvidenceKind.SECURITY,),
    "authentication.password_recovery": (EvidenceKind.PERSISTENCE, EvidenceKind.SECURITY),
    "authentication.security_error_paths": (EvidenceKind.PERSISTENCE, EvidenceKind.SECURITY),
}


@dataclass(frozen=True)
class AuthenticationJourneyVerification:
    journey_id: str
    required_step_ids: tuple[str, ...]
    claims: tuple[AuthenticationClaim, ...]
    evidence_kinds: tuple[EvidenceKind, ...]

    def __post_init__(self) -> None:
        _identifier(self.journey_id, "authentication journey ID")
        if (
            not isinstance(self.required_step_ids, tuple)
            or not self.required_step_ids
            or len(self.required_step_ids) > 100
            or any(not isinstance(value, str) or not _IDENTIFIER.fullmatch(value) for value in self.required_step_ids)
            or len(self.required_step_ids) != len(set(self.required_step_ids))
        ):
            raise ValueError("Authentication verification requires unique safe step IDs")
        if (
            not isinstance(self.claims, tuple)
            or not self.claims
            or any(not isinstance(value, AuthenticationClaim) for value in self.claims)
            or len(self.claims) != len(set(self.claims))
        ):
            raise ValueError("Authentication verification requires unique claims")
        allowed = {EvidenceKind.PERSISTENCE, EvidenceKind.SECURITY}
        if (
            not isinstance(self.evidence_kinds, tuple)
            or not self.evidence_kinds
            or not set(self.evidence_kinds) <= allowed
            or len(self.evidence_kinds) != len(set(self.evidence_kinds))
        ):
            raise ValueError("Authentication verification evidence kinds are invalid")
        if self.claims != LOCKED_AUTHENTICATION_CLAIMS.get(self.journey_id):
            raise ValueError("Authentication verification claims do not match the locked journey")
        if self.evidence_kinds != _LOCKED_EVIDENCE_KINDS.get(self.journey_id):
            raise ValueError("Authentication evidence kinds do not match the locked journey")


@dataclass(frozen=True)
class AuthenticationVerificationPlan:
    verification_id: str
    run_id: str
    product_id: str
    browser_plan_id: str
    browser_plan_digest: str
    configuration_id: str
    configuration_revision: int
    configuration_digest: str
    commit_sha: str
    acceptance_profile_id: str
    acceptance_profile_version: str
    acceptance_profile_digest: str
    provider_id: str
    journeys: tuple[AuthenticationJourneyVerification, ...]
    created_by: str
    created_at: datetime

    def __post_init__(self) -> None:
        for value, label in (
            (self.verification_id, "authentication verification ID"),
            (self.run_id, "authentication run ID"),
            (self.product_id, "authentication product ID"),
            (self.browser_plan_id, "authentication browser plan ID"),
            (self.configuration_id, "authentication configuration ID"),
            (self.acceptance_profile_id, "authentication profile ID"),
            (self.provider_id, "authentication provider ID"),
        ):
            _identifier(value, label)
        for value, label in (
            (self.browser_plan_digest, "browser plan digest"),
            (self.configuration_digest, "configuration digest"),
            (self.acceptance_profile_digest, "profile digest"),
        ):
            if not isinstance(value, str) or not _DIGEST.fullmatch(value):
                raise ValueError(f"{label} must be a lowercase SHA-256 digest")
        if not isinstance(self.commit_sha, str) or not _SHA.fullmatch(self.commit_sha):
            raise ValueError("Authentication plan requires a lowercase full commit SHA")
        if (
            isinstance(self.configuration_revision, bool)
            or not isinstance(self.configuration_revision, int)
            or self.configuration_revision < 1
        ):
            raise ValueError("Authentication configuration revision must be positive")
        _bounded(self.acceptance_profile_version, "profile version", 128)
        _bounded(self.created_by, "authentication plan creator", 256)
        if (
            not isinstance(self.journeys, tuple)
            or any(not isinstance(value, AuthenticationJourneyVerification) for value in self.journeys)
            or tuple(value.journey_id for value in self.journeys) != AUTHENTICATION_JOURNEYS
        ):
            raise ValueError("Authentication plan must contain every locked journey in order")
        _utc(self.created_at, "authentication plan created_at")

    @property
    def digest(self) -> str:
        payload = asdict(self)
        payload["created_at"] = self.created_at.isoformat()
        for journey in payload["journeys"]:
            journey["claims"] = [value.value for value in journey["claims"]]
            journey["evidence_kinds"] = [value.value for value in journey["evidence_kinds"]]
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        return hashlib.sha256(encoded).hexdigest()


def _identifier(value: str, label: str) -> None:
    if not isinstance(value, str) or not _IDENTIFIER.fullmatch(value):
        raise ValueError(f"{label} must be a safe identifier")


def _bounded(value: str, label: str, maximum: int) -> None:
    if (
        not isinstance(value, str)
        or not value
        or value != value.strip()
        or len(value) > maximum
        or any(ord(character) < 32 or ord(character) == 127 for character in value)
    ):
        raise ValueError(f"{label} must be bounded text")


def _utc(value: datetime, label: str) -> None:
    offset = value.utcoffset() if isinstance(value, datetime) else None
    if not isinstance(value, datetime) or value.tzinfo is None or offset is None or offset.total_seconds() != 0:
        raise ValueError(f"{label} must use UTC")
