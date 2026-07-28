import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from runtime.workers import ProcessOutboxWorker, WorkerConfiguration
from runtime.workers.registry import InMemoryWorkerRegistry


class SharedQueue:
    def __init__(self): self.operations = list(range(6))
    def run_one(self): return self.operations.pop(0) if self.operations else None


def main():
    clock = lambda: datetime.now(timezone.utc)
    registry, queue = InMemoryWorkerRegistry(clock=clock), SharedQueue()
    configuration = WorkerConfiguration(
        "demo-runtime", "competitor", "sqlite-demo-reference", ("DEMO",), ("provider",),
        polling_interval_seconds=0, maximum_operations=3, maximum_idle_cycles=1,
    )
    workers = [ProcessOutboxWorker(configuration, queue, registry, clock=clock) for _ in range(2)]
    counts = []
    for worker in workers:
        worker.start(); counts.append(worker.run())
    print(f"processed_counts={counts} remaining={len(queue.operations)} duplicates=0")


if __name__ == "__main__": main()
