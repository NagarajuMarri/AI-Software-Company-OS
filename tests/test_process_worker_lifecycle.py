from datetime import datetime, timezone
import pickle
from types import SimpleNamespace
import pytest

from runtime.workers.models import WorkerConfiguration, WorkerStatus
from runtime.workers.process_worker import (
    ProcessOutboxWorker, StaleWorkerResultError, validate_child_result,
)
from runtime.workers.registry import InMemoryWorkerRegistry
from runtime.workers.shutdown import ShutdownController

NOW = datetime(2026, 1, 1, tzinfo=timezone.utc)


class StubWorker:
    def __init__(self, results): self.results = list(results)
    def run_one(self): return self.results.pop(0) if self.results else None


def config(**changes):
    values = dict(
        runtime_id="runtime", worker_id_prefix="worker",
        persistence_reference="sqlite-ref",
        supported_operation_types=("DISPATCH",),
        supported_provider_ids=("provider",),
        polling_interval_seconds=0,
        maximum_operations=3,
        maximum_runtime_seconds=10,
        maximum_idle_cycles=2,
    )
    values.update(changes)
    return WorkerConfiguration(**values)


def runtime(results, **changes):
    repo = InMemoryWorkerRegistry(clock=lambda: NOW)
    item = ProcessOutboxWorker(
        config(**changes), StubWorker(results), repo, clock=lambda: NOW,
        sleep=lambda _: None,
    )
    return item, repo


def test_no_automatic_registration():
    item, repo = runtime([object()])
    assert repo.list() == ()


def test_explicit_start_registers_idle_worker():
    item, repo = runtime([])
    item.start()
    assert repo.get(item.instance_id).status == WorkerStatus.IDLE


def test_one_shot_processes_at_most_one():
    item, repo = runtime([object(), object()])
    item.start()
    assert item.run_once() == 1
    assert repo.get(item.instance_id).status == WorkerStatus.STOPPED


def test_bounded_operation_mode():
    item, _ = runtime([object()] * 5, maximum_operations=3)
    item.start()
    assert item.run() == 3


def test_idle_cycles_are_bounded():
    item, _ = runtime([], maximum_idle_cycles=2)
    item.start()
    assert item.run() == 0


def test_operator_stop_prevents_work():
    item, repo = runtime([object()])
    item.start(); item.stop()
    assert item.run() == 0
    assert repo.get(item.instance_id).status == WorkerStatus.STOPPED


def test_fatal_error_marks_failed():
    class Failing:
        def run_one(self): raise RuntimeError("failed")
    repo = InMemoryWorkerRegistry(clock=lambda: NOW)
    item = ProcessOutboxWorker(config(), Failing(), repo, clock=lambda: NOW)
    item.start()
    try: item.run()
    except RuntimeError: pass
    assert repo.get(item.instance_id).status == WorkerStatus.FAILED


def test_restart_has_new_instance_identity():
    first, _ = runtime([])
    second, _ = runtime([])
    assert first.instance_id != second.instance_id


def test_configuration_is_process_serialisable():
    restored = pickle.loads(pickle.dumps(config()))
    assert restored.persistence_reference == "sqlite-ref"


def test_shutdown_controller_is_explicit():
    shutdown = ShutdownController()
    assert not shutdown.requested
    shutdown.request()
    assert shutdown.requested


@pytest.mark.parametrize("forged", [
    None,
    {"schema": 2, "processed": 1, "instance_id": "worker"},
    {"schema": 1, "processed": -1, "instance_id": "worker"},
    {"schema": 1, "processed": 1, "instance_id": "worker", "secret": "x"},
])
def test_forged_child_result_is_rejected(forged):
    with pytest.raises(ValueError): validate_child_result(forged)


def test_valid_child_result_is_accepted():
    result = {"schema": 1, "processed": 2, "instance_id": "worker-1"}
    assert validate_child_result(result) == result


def test_stale_worker_result_is_rejected():
    item, repo = runtime([])
    item.start()
    repo.update_status(item.instance_id, WorkerStatus.STALE)
    with pytest.raises(StaleWorkerResultError):
        item._guard_result(
            object(), SimpleNamespace(owner_id=item.instance_id)
        )
