"""Typed, secret-safe failures for managed-product environment execution."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from runtime.managed_product_environment.models import EnvironmentObservation


class ManagedProductEnvironmentError(RuntimeError):
    """Base failure for the Day 6 exact-SHA environment boundary."""


class EnvironmentAuthorityError(ManagedProductEnvironmentError):
    """The requested persisted configuration or current policy is not authoritative."""


class EnvironmentExecutionError(ManagedProductEnvironmentError):
    """A bounded environment operation failed without exposing provider output."""

    def __init__(
        self,
        code: str,
        message: str,
        *,
        observation: EnvironmentObservation | None = None,
        reconciliation_required: bool = False,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.observation = observation
        self.reconciliation_required = reconciliation_required


class EnvironmentWorkspaceError(EnvironmentExecutionError):
    """The isolated source workspace could not be prepared or removed safely."""


class EnvironmentSecretResolutionError(EnvironmentExecutionError):
    """An opaque runtime secret reference could not be resolved safely."""


class EnvironmentCommandError(EnvironmentExecutionError):
    """A migration or declared service command failed."""


class EnvironmentReadinessError(EnvironmentExecutionError):
    """A declared service did not become ready within its bounded policy."""


class EnvironmentShutdownError(EnvironmentExecutionError):
    """A managed process could not be stopped through the declared lifecycle."""
