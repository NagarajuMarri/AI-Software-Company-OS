"""Write-once customer account and revocable session persistence."""

from __future__ import annotations

from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
from typing import Any

from runtime.customer_authentication.errors import (
    AccountAlreadyExists,
    AccountNotFound,
    AuthenticationAuthorityCorrupt,
    InvalidSession,
)
from runtime.customer_authentication.models import (
    CustomerAccount,
    CustomerSession,
    normalize_email,
)


_SCHEMA_VERSION = 1


class FileCustomerAccountStore:
    """Store one immutable account for each canonical-email digest."""

    def __init__(self, root: Path) -> None:
        self._root = root.resolve()
        self._root.mkdir(parents=True, exist_ok=True)

    def create(self, value: CustomerAccount) -> CustomerAccount:
        path = self._path(value.email)
        content = _encode("account", _account_record(value), value.digest)
        try:
            _exclusive_write(path, content)
        except FileExistsError:
            existing = self.load(value.email)
            if existing == value:
                return existing
            raise AccountAlreadyExists("Customer account already exists") from None
        return value

    def load(self, email: str) -> CustomerAccount:
        canonical = normalize_email(email)
        path = self._path(canonical)
        envelope = _read(path, AccountNotFound("Unknown customer account"))
        try:
            if envelope["kind"] != "account":
                raise ValueError("Wrong authority kind")
            value = _account_from_record(envelope["record"])
            if (
                value.email != canonical
                or value.digest != envelope["digest"]
                or _encode("account", _account_record(value), value.digest)
                != path.read_bytes()
            ):
                raise ValueError("Account authority mismatch")
            return value
        except (KeyError, TypeError, ValueError) as error:
            raise AuthenticationAuthorityCorrupt(
                "Customer account authority is corrupt"
            ) from error

    def _path(self, email: str) -> Path:
        canonical = normalize_email(email)
        name = hashlib.sha256(canonical.encode()).hexdigest()
        return _contained(self._root, self._root / "accounts" / f"{name}.json")


class FileCustomerSessionStore:
    """Store only bearer-token digests and durable revocation markers."""

    def __init__(self, root: Path) -> None:
        self._root = root.resolve()
        self._root.mkdir(parents=True, exist_ok=True)

    def create(self, value: CustomerSession) -> CustomerSession:
        path = self._session_path(value.token_digest)
        content = _encode("session", _session_record(value), value.digest)
        try:
            _exclusive_write(path, content)
        except FileExistsError:
            existing = self.load(value.token_digest)
            if existing == value:
                return existing
            raise InvalidSession("Customer session identity collision") from None
        return value

    def load(self, token_digest: str) -> CustomerSession:
        path = self._session_path(token_digest)
        if self._revoked_path(token_digest).exists():
            self._validate_revocation(token_digest)
            raise InvalidSession("Customer session is revoked")
        envelope = _read(path, InvalidSession("Unknown customer session"))
        try:
            if envelope["kind"] != "session":
                raise ValueError("Wrong authority kind")
            value = _session_from_record(envelope["record"])
            if (
                value.token_digest != token_digest
                or value.digest != envelope["digest"]
                or _encode("session", _session_record(value), value.digest)
                != path.read_bytes()
            ):
                raise ValueError("Session authority mismatch")
            return value
        except (KeyError, TypeError, ValueError) as error:
            raise AuthenticationAuthorityCorrupt(
                "Customer session authority is corrupt"
            ) from error

    def revoke(self, token_digest: str, revoked_at: datetime) -> None:
        # Loading first prevents revocation markers for invented session identities.
        self.load(token_digest)
        record: dict[str, object] = {
            "token_digest": token_digest,
            "revoked_at": revoked_at.isoformat(),
        }
        digest = hashlib.sha256(
            json.dumps(record, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        try:
            _exclusive_write(
                self._revoked_path(token_digest),
                _encode("revocation", record, digest),
            )
        except FileExistsError:
            return

    def _validate_revocation(self, token_digest: str) -> None:
        path = self._revoked_path(token_digest)
        envelope = _read(path, InvalidSession("Unknown customer revocation"))
        try:
            record = envelope["record"]
            if envelope["kind"] != "revocation" or set(record) != {
                "token_digest",
                "revoked_at",
            }:
                raise ValueError("Revocation authority fields are invalid")
            revoked_at = datetime.fromisoformat(record["revoked_at"])
            if revoked_at.tzinfo is None or revoked_at.utcoffset() is None:
                raise ValueError("Revocation time is not timezone-aware")
            digest = hashlib.sha256(
                json.dumps(record, sort_keys=True, separators=(",", ":")).encode()
            ).hexdigest()
            if record["token_digest"] != token_digest or envelope["digest"] != digest:
                raise ValueError("Revocation authority mismatch")
        except (KeyError, TypeError, ValueError) as error:
            raise AuthenticationAuthorityCorrupt(
                "Customer revocation authority is corrupt"
            ) from error

    def _session_path(self, token_digest: str) -> Path:
        _safe_digest(token_digest)
        return _contained(self._root, self._root / "sessions" / f"{token_digest}.json")

    def _revoked_path(self, token_digest: str) -> Path:
        _safe_digest(token_digest)
        return _contained(self._root, self._root / "sessions" / f"{token_digest}.revoked")


def _exclusive_write(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
    except Exception:
        try:
            path.unlink()
        except FileNotFoundError:
            pass
        raise


def _read(path: Path, missing: Exception) -> dict[str, Any]:
    if path.is_symlink():
        raise AuthenticationAuthorityCorrupt("Authentication authority file is unsafe")
    try:
        content = path.read_bytes()
    except FileNotFoundError:
        raise missing from None
    try:
        value = json.loads(content)
        if (
            not isinstance(value, dict)
            or set(value) != {"schema_version", "kind", "digest", "record"}
            or value["schema_version"] != _SCHEMA_VERSION
            or not isinstance(value["record"], dict)
            or _encode(value["kind"], value["record"], value["digest"]) != content
        ):
            raise ValueError("Invalid authority envelope")
        return value
    except (TypeError, ValueError, json.JSONDecodeError) as error:
        raise AuthenticationAuthorityCorrupt(
            "Authentication authority is corrupt"
        ) from error


def _encode(kind: str, record: dict[str, object], digest: str) -> bytes:
    envelope = {
        "schema_version": _SCHEMA_VERSION,
        "kind": kind,
        "digest": digest,
        "record": record,
    }
    return (
        json.dumps(envelope, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        + "\n"
    ).encode()


def _account_record(value: CustomerAccount) -> dict[str, object]:
    return {
        "customer_id": value.customer_id,
        "email": value.email,
        "password_salt": value.password_salt,
        "password_digest": value.password_digest,
        "created_at": value.created_at.isoformat(),
    }


def _account_from_record(value: dict[str, Any]) -> CustomerAccount:
    if set(value) != {
        "customer_id",
        "email",
        "password_salt",
        "password_digest",
        "created_at",
    }:
        raise ValueError("Customer account fields are invalid")
    return CustomerAccount(
        value["customer_id"],
        value["email"],
        value["password_salt"],
        value["password_digest"],
        datetime.fromisoformat(value["created_at"]),
    )


def _session_record(value: CustomerSession) -> dict[str, object]:
    return {
        "token_digest": value.token_digest,
        "customer_id": value.customer_id,
        "csrf_token": value.csrf_token,
        "created_at": value.created_at.isoformat(),
        "expires_at": value.expires_at.isoformat(),
    }


def _session_from_record(value: dict[str, Any]) -> CustomerSession:
    if set(value) != {
        "token_digest",
        "customer_id",
        "csrf_token",
        "created_at",
        "expires_at",
    }:
        raise ValueError("Customer session fields are invalid")
    return CustomerSession(
        value["token_digest"],
        value["customer_id"],
        value["csrf_token"],
        datetime.fromisoformat(value["created_at"]),
        datetime.fromisoformat(value["expires_at"]),
    )


def _safe_digest(value: object) -> None:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise InvalidSession("Customer session digest is invalid")


def _contained(root: Path, path: Path) -> Path:
    parent = path.parent.resolve()
    if root not in (parent, *parent.parents):
        raise AuthenticationAuthorityCorrupt("Authentication path escaped its store")
    return path
