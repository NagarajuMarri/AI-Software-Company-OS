"""Exact-commit PWA verification and complete capability aggregation."""

from runtime.managed_product_pwa.contracts import (
    AcceptanceSubmissionStore,
    PwaVerificationPlanStore,
)
from runtime.managed_product_pwa.errors import (
    AcceptanceSubmissionError,
    PwaPlanError,
    PwaVerificationError,
)
from runtime.managed_product_pwa.models import (
    AcceptanceSubmissionPlan,
    AcceptanceSubmissionReceipt,
    CapabilityExecutionReference,
    LOCKED_CAPABILITY_ORDER,
    LOCKED_PWA_CLAIMS,
    PwaClaim,
    PwaExecutionPolicy,
    PwaVerificationPlan,
)
from runtime.managed_product_pwa.persistence import (
    FileAcceptanceSubmissionStore,
    FilePwaVerificationPlanStore,
    InMemoryAcceptanceSubmissionStore,
    InMemoryPwaVerificationPlanStore,
)
from runtime.managed_product_pwa.provider import PlaywrightPwaProvider
from runtime.managed_product_pwa.service import (
    ManagedProductPwaService,
    RuntimeAcceptanceAggregator,
)

__all__ = [
    "AcceptanceSubmissionError",
    "AcceptanceSubmissionPlan",
    "AcceptanceSubmissionReceipt",
    "AcceptanceSubmissionStore",
    "CapabilityExecutionReference",
    "FileAcceptanceSubmissionStore",
    "FilePwaVerificationPlanStore",
    "InMemoryAcceptanceSubmissionStore",
    "InMemoryPwaVerificationPlanStore",
    "LOCKED_CAPABILITY_ORDER",
    "LOCKED_PWA_CLAIMS",
    "ManagedProductPwaService",
    "PlaywrightPwaProvider",
    "PwaClaim",
    "PwaExecutionPolicy",
    "PwaPlanError",
    "PwaVerificationError",
    "PwaVerificationPlan",
    "PwaVerificationPlanStore",
    "RuntimeAcceptanceAggregator",
]
