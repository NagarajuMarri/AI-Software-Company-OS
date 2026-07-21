from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Generic, TypeVar

T = TypeVar("T")


class Repository(ABC, Generic[T]):
    """Abstract repository interface for runtime persistence operations."""

    @abstractmethod
    def add(self, item: T) -> T:
        """Persist a new item."""

    @abstractmethod
    def get(self, item_id: str) -> T:
        """Retrieve an item by identifier."""
