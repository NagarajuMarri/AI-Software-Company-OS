from dataclasses import dataclass
from datetime import timedelta

from runtime.integrations.github.exceptions import (
    ExternalProviderUnavailableError, GitHubAuthenticationError,
    GitHubRateLimitError,
)
from runtime.outbox.models import FailureCategory


@dataclass(frozen=True)
class RetryDecision:
    category: FailureCategory
    retry_at: object | None
    code: str


class RetryPolicy:
    def __init__(self, *, base_seconds=1, maximum_seconds=60):
        self.base_seconds = base_seconds
        self.maximum_seconds = maximum_seconds

    def classify(self, error, operation, now):
        if isinstance(error, GitHubAuthenticationError):
            return RetryDecision(FailureCategory.NON_RETRYABLE, None, "AUTHENTICATION")
        if isinstance(error, GitHubRateLimitError):
            seconds = getattr(error, "retry_after_seconds", self.base_seconds)
            return RetryDecision(FailureCategory.RATE_LIMITED, now + timedelta(seconds=seconds), "RATE_LIMIT")
        if isinstance(error, TimeoutError):
            return RetryDecision(FailureCategory.RECONCILIATION_REQUIRED, None, "TIMEOUT_UNCERTAIN")
        if isinstance(error, ExternalProviderUnavailableError):
            seconds = min(
                self.maximum_seconds,
                self.base_seconds * (2 ** max(operation.attempt_count - 1, 0)),
            )
            return RetryDecision(FailureCategory.RETRYABLE_BACKOFF, now + timedelta(seconds=seconds), "PROVIDER_UNAVAILABLE")
        return RetryDecision(FailureCategory.NON_RETRYABLE, None, type(error).__name__.upper())
