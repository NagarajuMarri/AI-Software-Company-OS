"""Explicit process-capable lifecycle around the deterministic outbox worker."""

import os
import time
from datetime import timedelta
from uuid import uuid4

from runtime.workers.models import WorkerRegistration, WorkerStatus
from runtime.workers.shutdown import ShutdownController


class StaleWorkerResultError(RuntimeError):
    pass


def validate_child_result(value):
    if (
        not isinstance(value, dict)
        or set(value) != {"schema", "processed", "instance_id"}
        or value.get("schema") != 1
        or not isinstance(value.get("processed"), int)
        or not 0 <= value["processed"] <= 10_000
        or not isinstance(value.get("instance_id"), str)
        or not 1 <= len(value["instance_id"]) <= 160
    ):
        raise ValueError("Invalid worker child result")
    return value


class ProcessOutboxWorker:
    def __init__(
        self, configuration, worker, registry, *, clock,
        sleep=time.sleep, shutdown=None, node_reference="local-node",
    ):
        self.configuration = configuration
        self.worker = worker
        self.registry = registry
        self.clock = clock
        self.sleep = sleep
        self.shutdown = shutdown or ShutdownController()
        self.node_reference = node_reference
        self.instance_id = f"{configuration.worker_id_prefix}-{uuid4().hex}"
        self.processed = 0

    def _guard_result(self, operation, claim):
        registration = self.registry.get(self.instance_id)
        if (
            registration.status in {
                WorkerStatus.STALE, WorkerStatus.FAILED,
                WorkerStatus.STOPPED, WorkerStatus.UNHEALTHY,
            }
            or registration.heartbeat_expires_at <= self.clock()
            or claim.owner_id != self.instance_id
        ):
            raise StaleWorkerResultError("Worker result authority expired")

    def start(self):
        now = self.clock()
        registration = WorkerRegistration(
            worker_id=self.configuration.worker_id_prefix,
            worker_instance_id=self.instance_id,
            process_id=os.getpid(),
            node_reference=self.node_reference,
            runtime_id=self.configuration.runtime_id,
            worker_type="OUTBOX",
            supported_operation_types=self.configuration.supported_operation_types,
            supported_provider_capabilities=self.configuration.supported_provider_ids,
            status=WorkerStatus.STARTING,
            started_at=now, registered_at=now, last_heartbeat_at=now,
            heartbeat_expires_at=now + timedelta(
                seconds=self.configuration.heartbeat_timeout_seconds
            ),
        )
        self.registry.register(registration)
        if hasattr(self.worker, "worker_id"):
            self.worker.worker_id = self.instance_id
        if hasattr(self.worker, "result_guard"):
            previous_guard = self.worker.result_guard
            def guarded(operation, claim):
                if previous_guard is not None:
                    previous_guard(operation, claim)
                self._guard_result(operation, claim)
            self.worker.result_guard = guarded
        self.registry.update_status(self.instance_id, WorkerStatus.IDLE)
        return registration

    def run(self, *, one_shot=False):
        started = self.clock()
        idle = 0
        try:
            while (
                not self.shutdown.requested
                and self.processed < self.configuration.maximum_operations
                and (self.clock() - started).total_seconds()
                    < self.configuration.maximum_runtime_seconds
                and idle < self.configuration.maximum_idle_cycles
            ):
                registered = self.registry.get(self.instance_id)
                if registered.shutdown_requested: break
                self.registry.heartbeat(
                    self.instance_id,
                    timeout_seconds=self.configuration.heartbeat_timeout_seconds,
                )
                self.registry.update_status(self.instance_id, WorkerStatus.CLAIMING)
                result = self.worker.run_one()
                if result is None:
                    idle += 1
                else:
                    idle = 0
                    self.processed += 1
                self.registry.update_status(self.instance_id, WorkerStatus.IDLE)
                if one_shot: break
                if self.configuration.polling_interval_seconds:
                    self.sleep(self.configuration.polling_interval_seconds)
            self.registry.mark_stopped(self.instance_id)
            return self.processed
        except BaseException:
            self.registry.mark_failed(self.instance_id)
            raise

    def run_once(self):
        return self.run(one_shot=True)

    def stop(self):
        self.shutdown.request()


def process_entrypoint(configuration, composition_name, result_queue):
    """Spawn-safe entrypoint; resolves dependencies inside the child."""
    from runtime.workers.lifecycle import get_composition_factory
    if not isinstance(composition_name, str) or len(composition_name) > 128:
        raise ValueError("Invalid composition reference")
    runtime = get_composition_factory(composition_name)(configuration)
    processed = runtime.run()
    result_queue.put(validate_child_result({
        "schema": 1, "processed": processed, "instance_id": runtime.instance_id,
    }))
