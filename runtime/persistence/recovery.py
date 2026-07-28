"""Restoration facade."""

from runtime.persistence.service import RuntimePersistenceService


class RuntimeRecoveryService:
    def __init__(self, persistence_service: RuntimePersistenceService) -> None:
        self.persistence_service = persistence_service

    def restore_latest(self):
        checkpoint = self.persistence_service.load_latest_checkpoint()
        return self.persistence_service.restore_runtime(checkpoint)
