"""Atomic JSON file-backed outbox repository."""

import json
import os
from pathlib import Path

from runtime.outbox.providers.serde import decode_state, encode_state
from runtime.outbox.repository import InMemoryOutboxRepository


class FileOutboxRepository(InMemoryOutboxRepository):
    def __init__(self, path, *, clock=None):
        self.path = Path(path).resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        super().__init__(clock=clock)
        if self.path.exists():
            self.import_state(
                decode_state(json.loads(self.path.read_text(encoding="utf-8")))
            )

    def _persist(self):
        temporary = self.path.with_suffix(self.path.suffix + ".tmp")
        temporary.write_text(
            json.dumps(encode_state(self.export_state()), sort_keys=True),
            encoding="utf-8",
        )
        os.replace(temporary, self.path)

    def _mutate(self, method, *args, **kwargs):
        result = method(*args, **kwargs)
        self._persist()
        return result

    def add_operation(self, value): return self._mutate(super().add_operation, value)
    def claim_next(self, *a, **k): return self._mutate(super().claim_next, *a, **k)
    def claim_reconciliation(self, *a, **k): return self._mutate(super().claim_reconciliation, *a, **k)
    def renew_claim(self, *a, **k): return self._mutate(super().renew_claim, *a, **k)
    def release_claim(self, *a, **k): return self._mutate(super().release_claim, *a, **k)
    def mark_dispatching(self, *a, **k): return self._mutate(super().mark_dispatching, *a, **k)
    def mark_succeeded(self, *a, **k): return self._mutate(super().mark_succeeded, *a, **k)
    def mark_retry_wait(self, *a, **k): return self._mutate(super().mark_retry_wait, *a, **k)
    def mark_reconciliation_required(self, *a, **k): return self._mutate(super().mark_reconciliation_required, *a, **k)
    def mark_dead_letter(self, *a, **k): return self._mutate(super().mark_dead_letter, *a, **k)
    def cancel_operation(self, *a, **k): return self._mutate(super().cancel_operation, *a, **k)
    def abandon_operation(self, *a, **k): return self._mutate(super().abandon_operation, *a, **k)
    def retry_dead_letter(self, *a, **k): return self._mutate(super().retry_dead_letter, *a, **k)
    def pause_provider(self, *a, **k): return self._mutate(super().pause_provider, *a, **k)
    def resume_provider(self, *a, **k): return self._mutate(super().resume_provider, *a, **k)
    def recover_expired(self, *a, **k): return self._mutate(super().recover_expired, *a, **k)
