"""Customer registration, login, session authentication, and logout."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timedelta, timezone
import hashlib
import hmac
from secrets import token_bytes, token_urlsafe

from runtime.customer_authentication.errors import (
    AccountNotFound,
    InvalidCredentials,
    InvalidSession,
)
from runtime.customer_authentication.models import (
    CustomerAccount,
    CustomerSession,
    IssuedCustomerSession,
    normalize_email,
)
from runtime.customer_authentication.persistence import (
    FileCustomerAccountStore,
    FileCustomerSessionStore,
)


_SESSION_LIFETIME = timedelta(hours=12)
_FAKE_SALT = bytes.fromhex("7f34a179e28f169af57c8c82dd91cf5c")
_FAKE_DIGEST = hashlib.scrypt(
    b"invalid-customer-password",
    salt=_FAKE_SALT,
    n=2**14,
    r=8,
    p=1,
    dklen=32,
)


class CustomerAuthenticationService:
    """Own customer credentials while keeping raw secrets invocation-only."""

    def __init__(
        self,
        accounts: FileCustomerAccountStore,
        sessions: FileCustomerSessionStore,
        *,
        clock: Callable[[], datetime] | None = None,
        token_factory: Callable[[], str] | None = None,
        salt_factory: Callable[[], bytes] | None = None,
    ) -> None:
        self._accounts = accounts
        self._sessions = sessions
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._token_factory = token_factory or (lambda: token_urlsafe(32))
        self._salt_factory = salt_factory or (lambda: token_bytes(16))

    def register(self, email: str, password: str) -> IssuedCustomerSession:
        canonical = normalize_email(email)
        _password_policy(password)
        salt = self._salt_factory()
        if len(salt) != 16:
            raise ValueError("Customer password salt factory is invalid")
        account = CustomerAccount(
            f"customer-{self._token_factory()}",
            canonical,
            salt.hex(),
            _password_digest(password, salt).hex(),
            self._clock(),
        )
        self._accounts.create(account)
        return self._issue(account.customer_id)

    def login(self, email: str, password: str) -> IssuedCustomerSession:
        try:
            canonical = normalize_email(email)
            account = self._accounts.load(canonical)
        except (ValueError, AccountNotFound):
            _verify_fake(password)
            raise InvalidCredentials("Invalid email or password") from None
        observed = _password_digest(password, bytes.fromhex(account.password_salt))
        if not hmac.compare_digest(observed.hex(), account.password_digest):
            raise InvalidCredentials("Invalid email or password")
        return self._issue(account.customer_id)

    def authenticate(self, token: str) -> CustomerSession:
        digest = _token_digest(token)
        session = self._sessions.load(digest)
        if session.expires_at <= self._clock():
            try:
                self._sessions.revoke(digest, self._clock())
            except InvalidSession:
                pass
            raise InvalidSession("Customer session expired")
        return session

    def logout(self, token: str) -> None:
        digest = _token_digest(token)
        try:
            self._sessions.revoke(digest, self._clock())
        except InvalidSession:
            # Logout is idempotent and does not disclose whether a token existed.
            return

    def _issue(self, customer_id: str) -> IssuedCustomerSession:
        token = self._token_factory()
        csrf = self._token_factory()
        if token == csrf:
            raise ValueError("Session and CSRF token factories must produce distinct values")
        now = self._clock()
        session = CustomerSession(
            _token_digest(token),
            customer_id,
            csrf,
            now,
            now + _SESSION_LIFETIME,
        )
        self._sessions.create(session)
        return IssuedCustomerSession(token, session)


def _password_policy(value: object) -> None:
    if (
        not isinstance(value, str)
        or not 12 <= len(value) <= 128
        or any(ord(character) < 32 or ord(character) == 127 for character in value)
        or not any(character.islower() for character in value)
        or not any(character.isupper() for character in value)
        or not any(character.isdigit() for character in value)
    ):
        raise ValueError(
            "Password must contain 12-128 characters with upper, lower, and number"
        )


def _password_digest(value: str, salt: bytes) -> bytes:
    return hashlib.scrypt(
        value.encode(),
        salt=salt,
        n=2**14,
        r=8,
        p=1,
        dklen=32,
    )


def _verify_fake(value: object) -> None:
    password = value if isinstance(value, str) else ""
    observed = _password_digest(password, _FAKE_SALT)
    hmac.compare_digest(observed, _FAKE_DIGEST)


def _token_digest(value: object) -> str:
    if (
        not isinstance(value, str)
        or not 32 <= len(value) <= 256
        or any(not (character.isalnum() or character in "_-") for character in value)
    ):
        raise InvalidSession("Customer session token is invalid")
    return hashlib.sha256(value.encode()).hexdigest()
