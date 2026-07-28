"""Safe demonstration composition imported inside a spawned child process."""
from datetime import datetime, timezone

from runtime.workers.process_worker import ProcessOutboxWorker
from runtime.workers.registry import InMemoryWorkerRegistry


class _BoundedWorker:
    def __init__(self, maximum): self.remaining = maximum
    def run_one(self):
        if self.remaining <= 0: return None
        self.remaining -= 1
        return self.remaining


def create_demo_worker(configuration):
    clock = lambda: datetime.now(timezone.utc)
    registry = InMemoryWorkerRegistry(clock=clock)
    runtime = ProcessOutboxWorker(
        configuration, _BoundedWorker(configuration.maximum_operations),
        registry, clock=clock,
    )
    runtime.start()
    return runtime
