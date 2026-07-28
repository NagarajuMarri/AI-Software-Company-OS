"""Shallow identity-preserving snapshots for mutable runtime state."""

from dataclasses import dataclass

from runtime.exceptions import TransactionRollbackError


@dataclass
class MutableSnapshot:
    """Capture a mutable object's direct state without replacing aggregates."""

    target: object
    state: object

    @classmethod
    def capture(cls, target: object) -> "MutableSnapshot":
        if isinstance(target, dict):
            return cls(target, dict(target))
        if isinstance(target, list):
            return cls(target, list(target))
        if isinstance(target, set):
            return cls(target, set(target))
        if hasattr(target, "__dict__"):
            return cls(target, dict(vars(target)))
        raise TransactionRollbackError(
            f"Unsupported transaction snapshot target: {type(target).__name__}"
        )

    def restore(self) -> None:
        try:
            if isinstance(self.target, dict):
                self.target.clear()
                self.target.update(self.state)
            elif isinstance(self.target, list):
                self.target[:] = self.state
            elif isinstance(self.target, set):
                self.target.clear()
                self.target.update(self.state)
            else:
                vars(self.target).clear()
                vars(self.target).update(self.state)
        except Exception as error:
            raise TransactionRollbackError(
                "Failed to restore transaction snapshot"
            ) from error
