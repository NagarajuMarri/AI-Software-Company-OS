from runtime.workers.supervisor import WorkerSupervisor


def test_supervisor_runs_bounded_cycle(operation_factory, worker_factory):
    worker, repository, _, _ = worker_factory()
    repository.add_operation(operation_factory())
    supervisor = WorkerSupervisor(repository)
    supervisor.register_worker(worker)
    supervisor.run_one_cycle()
    assert supervisor.health().backlog == 0
    assert supervisor.health().last_successful_cycle is not None


def test_supervisor_rejects_duplicate_worker(worker_factory):
    import pytest
    worker, repository, _, _ = worker_factory()
    supervisor = WorkerSupervisor(repository)
    supervisor.register_worker(worker)
    with pytest.raises(ValueError):
        supervisor.register_worker(worker)


def test_supervisor_stops_without_background_thread(worker_factory):
    worker, repository, _, _ = worker_factory()
    supervisor = WorkerSupervisor(repository)
    supervisor.register_worker(worker)
    supervisor.stop()
    assert not supervisor.health().healthy
    assert supervisor.run_one_cycle() == ()
