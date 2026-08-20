"""Typed failures for the customer project-progress projection."""

from __future__ import annotations


class CustomerProjectProgressError(RuntimeError):
    """Base failure for the customer progress boundary."""


class CustomerProjectProgressConflict(CustomerProjectProgressError):
    """Required exact planning authority is not available."""


class CustomerProjectProgressCorrupt(CustomerProjectProgressError):
    """The upstream authority chain cannot produce a safe projection."""
