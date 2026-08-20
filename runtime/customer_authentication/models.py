"""Customer account and session authority models."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
import hashlib
import json
import re


_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")
_DIGEST = re.compile(r"^[0-9a-f]{64}$")
_SALT = re.compile(r"^[0-9a-f]{32}$")
_CSRF = re.compile(r"^[A-Za-z0-9_-]{32,256}$")


@dataclass(frozen=True)
class CustomerAccount:
    """One immutable customer credential record."""

    customer_id: str
    email: str
    password_salt: str
    password_digest: str
    created_at: datetime

    def __post_init__(self) -> None:
        _identifier(self.customer_id, "customer ID")
        if normalize_email(self.email) != self.email:
            raise ValueError("Customer email is not canonical")
        if not _SALT.fullmatch(self.password_salt):
            raise ValueError("Customer password salt is invalid")
        _digest(self.password_digest, "customer password digest")
        _utc(self.created_at, "customer account created_at")

    @property
    def digest(self) -> str:
        return _hash(self)


@dataclass(frozen=True)
class CustomerSession:
    """A server-side session containing no raw bearer token."""

    token_digest: str
    customer_id: str
    csrf_token: str
    created_at: datetime
    expires_at: datetime

    def __post_init__(self) -> None:
        _digest(self.token_digest, "customer session token digest")
        _identifier(self.customer_id, "customer session customer ID")
        if not isinstance(self.csrf_token, str) or not _CSRF.fullmatch(self.csrf_token):
            raise ValueError("Customer session CSRF token is invalid")
        _utc(self.created_at, "customer session created_at")
        _utc(self.expires_at, "customer session expires_at")
        if (
            self.expires_at <= self.created_at
            or self.expires_at - self.created_at > timedelta(days=30)
        ):
            raise ValueError("Customer session lifetime is outside policy")

    @property
    def digest(self) -> str:
        return _hash(self)


@dataclass(frozen=True)
class IssuedCustomerSession:
    """Invocation-only bearer token plus its persisted safe authority."""

    token: str
    session: CustomerSession


def normalize_email(value: object) -> str:
    if not isinstance(value, str):
        raise ValueError("Customer email is invalid")
    canonical = value.strip().casefold()
    if (
        canonical != value.strip().lower()
        or len(canonical) > 254
        or canonical.count("@") != 1
        or any(ord(character) > 127 or character.isspace() for character in canonical)
    ):
        raise ValueError("Customer email is invalid")
    local, domain = canonical.split("@", 1)
    labels = domain.split(".")
    if (
        not 1 <= len(local) <= 64
        or local.startswith(".")
        or local.endswith(".")
        or ".." in local
        or len(labels) < 2
        or any(
            not label
            or len(label) > 63
            or label.startswith("-")
            or label.endswith("-")
            or not all(character.isalnum() or character == "-" for character in label)
            for label in labels
        )
    ):
        raise ValueError("Customer email is invalid")
    return canonical


def _identifier(value: object, label: str) -> None:
    if not isinstance(value, str) or not _IDENTIFIER.fullmatch(value):
        raise ValueError(f"{label} is invalid")


def _digest(value: object, label: str) -> None:
    if not isinstance(value, str) or not _DIGEST.fullmatch(value):
        raise ValueError(f"{label} is invalid")


def _utc(value: object, label: str) -> None:
    if (
        not isinstance(value, datetime)
        or value.tzinfo is None
        or value.utcoffset() is None
    ):
        raise ValueError(f"{label} must be timezone-aware")


def _hash(value: CustomerAccount | CustomerSession) -> str:
    payload = asdict(value)
    payload["created_at"] = value.created_at.isoformat()
    if isinstance(value, CustomerSession):
        payload["expires_at"] = value.expires_at.isoformat()
    content = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(content).hexdigest()
