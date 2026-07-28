from datetime import datetime, timezone

from runtime.outbox.models import OutboxStatus
from runtime.workers.models import WorkerHealth


class WorkerSupervisor:
    def __init__(self, repository):
        self.repository = repository
        self._workers = {}
        self._last_success = None
        self._stopped = False

    def register_worker(self, worker):
        if worker.worker_id in self._workers:
            raise ValueError("Duplicate worker")
        self._workers[worker.worker_id] = worker

    def run_one_cycle(self):
        if self._stopped: return ()
        results = tuple(worker.run_one() for worker in self._workers.values())
        self._last_success = datetime.now(timezone.utc)
        return results

    def run_cycles(self, maximum):
        return tuple(self.run_one_cycle() for _ in range(maximum))

    def stop(self):
        self._stopped = True
        for worker in self._workers.values(): worker.stop()

    def health(self):
        values = self.repository.list_operations()
        return WorkerHealth(
            not self._stopped, self._last_success,
            sum(item.status in {OutboxStatus.CLAIMED, OutboxStatus.DISPATCHING} for item in values),
            len(self.repository.list_pending_operations()),
            sum(item.status == OutboxStatus.DEAD_LETTER for item in values),
            sum(item.status == OutboxStatus.RECONCILIATION_REQUIRED for item in values),
        )
