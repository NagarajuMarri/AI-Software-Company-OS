"""Exact-commit authentication persistence and security verification."""

from runtime.managed_product_authentication.contracts import (
    AuthenticationVerificationPlanStore,
)
from runtime.managed_product_authentication.errors import (
    AuthenticationPlanError,
    AuthenticationVerificationError,
)
from runtime.managed_product_authentication.models import (
    AuthenticationClaim,
    AuthenticationJourneyVerification,
    AuthenticationVerificationPlan,
    LOCKED_AUTHENTICATION_CLAIMS,
)
from runtime.managed_product_authentication.persistence import (
    FileAuthenticationVerificationPlanStore,
    InMemoryAuthenticationVerificationPlanStore,
)
from runtime.managed_product_authentication.provider import (
    AuthenticationEvidenceBrowserProvider,
)

__all__ = [
    "AuthenticationClaim",
    "AuthenticationEvidenceBrowserProvider",
    "AuthenticationJourneyVerification",
    "AuthenticationPlanError",
    "AuthenticationVerificationError",
    "AuthenticationVerificationPlan",
    "AuthenticationVerificationPlanStore",
    "FileAuthenticationVerificationPlanStore",
    "InMemoryAuthenticationVerificationPlanStore",
    "LOCKED_AUTHENTICATION_CLAIMS",
]
