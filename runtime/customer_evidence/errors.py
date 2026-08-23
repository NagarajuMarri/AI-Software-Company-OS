"""Typed failures for the customer Preview and Evidence Centre."""

from __future__ import annotations


class CustomerEvidenceError(RuntimeError):
    """Base failure for the customer evidence boundary."""


class CustomerEvidenceConflict(CustomerEvidenceError):
    """Exact preview, evidence, or review authority is unavailable."""


class CustomerEvidenceCorrupt(CustomerEvidenceError):
    """Persisted preview or review authority failed closed validation."""


class CustomerEvidenceNotFound(CustomerEvidenceError):
    """A requested preview evidence package does not exist."""
