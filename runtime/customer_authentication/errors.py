"""Customer authentication errors."""


class CustomerAuthenticationError(Exception):
    """Base customer authentication error."""


class AccountAlreadyExists(CustomerAuthenticationError):
    """The canonical email already owns an account."""


class AccountNotFound(CustomerAuthenticationError):
    """No account exists for the canonical email."""


class AuthenticationAuthorityCorrupt(CustomerAuthenticationError):
    """Persisted account or session authority failed integrity checks."""


class InvalidCredentials(CustomerAuthenticationError):
    """Login credentials were invalid."""


class InvalidSession(CustomerAuthenticationError):
    """The session is missing, revoked, expired, or malformed."""
