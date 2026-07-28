"""External task coordination with explicit side-effect records."""

from contextlib import nullcontext
from datetime import datetime, timezone
from uuid import uuid4

from runtime.coding_agents.models import CodingAgentResultStatus
from runtime.events.types import EventType
from runtime.tasks.approval import decision
from runtime.tasks.exceptions import (
    ApprovalPolicyError,
    ExternalTaskNotFoundError,
    InvalidExternalTaskTransitionError,
)
from runtime.tasks.lifecycle import ALLOWED_TRANSITIONS
from runtime.tasks.models import (
    ApprovalStatus,
    ExternalOperation,
    ExternalOperationStatus,
    ExternalTask,
    ExternalTaskStatus,
)
from runtime.transactions.transaction import atomic_domain_operation


class ExternalTaskService:
    def __init__(self, registry, workspace_provider=None, event_publisher=None):
        self.registry = registry
        self.workspace_provider = workspace_provider
        self.event_publisher = event_publisher
        self._tasks = {}
        self._progress = {}
        self._results = {}
        self._decisions = {}
        self._operations = {}
        if event_publisher is not None:
            event_publisher.register_snapshot_provider(self._snapshot_targets)

    def _snapshot_targets(self):
        return [self]

    @atomic_domain_operation
    def create_task(self, **values):
        task_id = values["task_id"]
        if task_id in self._tasks:
            raise InvalidExternalTaskTransitionError("Task already exists")
        now = datetime.now(timezone.utc)
        task = ExternalTask(
            task_id, values["project_id"], values["work_item_id"],
            values.get("task_type", "CODING"), values["title"],
            values["description"], None, None,
            values["repository_reference"], values.get("base_branch", "main"),
            values["working_branch"], ExternalTaskStatus.CREATED,
            tuple(values.get("requested_capabilities", ())), now,
            correlation_id=values.get("correlation_id"),
            causation_id=values.get("causation_id"),
        )
        self._tasks[task_id] = task
        self._emit(EventType.EXTERNAL_TASK_CREATED, task, {"status": task.status.value})
        return task

    @atomic_domain_operation
    def queue_task(self, task_id):
        task = self.get_task(task_id)
        provider = self.registry.choose_compatible_provider(
            task.requested_capabilities
        )
        task.provider_id = provider.provider_id
        if self.workspace_provider and task.workspace_id is None:
            task.workspace_id = f"task-{task.task_id}"
            self.workspace_provider.create_workspace(task.workspace_id)
        self._transition(task, ExternalTaskStatus.QUEUED)
        self._emit(EventType.EXTERNAL_TASK_PROVIDER_SELECTED, task, {"provider_id": provider.provider_id})
        self._emit(EventType.EXTERNAL_TASK_QUEUED, task, {"status": task.status.value})
        return task

    def execute_task(self, task_id, request):
        task = self.get_task(task_id)
        with self._atomic():
            self._transition(task, ExternalTaskStatus.RUNNING)
            task.started_at = datetime.now(timezone.utc)
            self._emit(EventType.EXTERNAL_TASK_STARTED, task, {"status": task.status.value})
            operation = self._operation(task, "CODING_AGENT_SUBMIT")
            self._emit(EventType.EXTERNAL_OPERATION_PLANNED, task, {"operation_id": operation.operation_id})
            operation.status = ExternalOperationStatus.STARTED
            operation.updated_at = datetime.now(timezone.utc)
            self._emit(EventType.EXTERNAL_OPERATION_STARTED, task, {"operation_id": operation.operation_id})
        try:
            provider = self.registry.get_provider(task.provider_id)
            provider_task_id = provider.submit_task(request)
            progress = provider.get_progress(provider_task_id)
            result = provider.get_result(provider_task_id)
            self._validate_provider_progress(task_id, progress)
            if result.task_id != task_id:
                raise ValueError("Provider result belongs to another task")
        except Exception:
            with self._atomic():
                operation.status = ExternalOperationStatus.RECONCILIATION_REQUIRED
                operation.updated_at = datetime.now(timezone.utc)
                task.status = ExternalTaskStatus.RECONCILIATION_REQUIRED
                self._emit(EventType.EXTERNAL_OPERATION_RECONCILIATION_REQUIRED, task, {"operation_id": operation.operation_id})
            raise
        with self._atomic():
            self._progress[task_id] = list(progress)
            for item in progress:
                self._emit(
                    EventType.EXTERNAL_TASK_PROGRESS_RECORDED,
                    task,
                    {"sequence": item.sequence, "stage": item.stage},
                )
            self._results[task_id] = result
            operation.status = ExternalOperationStatus.SUCCEEDED
            operation.updated_at = datetime.now(timezone.utc)
            self._emit(EventType.EXTERNAL_OPERATION_SUCCEEDED, task, {"operation_id": operation.operation_id})
            if result.status == CodingAgentResultStatus.SUCCEEDED:
                task.result_reference = provider_task_id
            else:
                task.failure_code = result.failure_code
                self._transition(task, ExternalTaskStatus.FAILED)
                self._emit(EventType.EXTERNAL_TASK_FAILED, task, {"failure_code": task.failure_code})
        return result

    @atomic_domain_operation
    def request_review(self, task_id):
        task = self.get_task(task_id)
        if task.status != ExternalTaskStatus.RUNNING or task.result_reference is None:
            raise InvalidExternalTaskTransitionError(
                "Successful result is required before review"
            )
        task.approval_status = ApprovalStatus.PENDING
        self._transition(task, ExternalTaskStatus.WAITING_FOR_REVIEW)
        self._emit(EventType.EXTERNAL_TASK_REVIEW_REQUESTED, task, {"status": task.status.value})
        return task

    @atomic_domain_operation
    def retry_task(self, task_id):
        task = self.get_task(task_id)
        if task.status not in {ExternalTaskStatus.FAILED, ExternalTaskStatus.CHANGES_REQUESTED}:
            raise InvalidExternalTaskTransitionError("Task is not retryable")
        result = self._results.get(task_id)
        if (
            task.status == ExternalTaskStatus.FAILED
            and (
                result is None
                or result.status
                != CodingAgentResultStatus.FAILED_RETRYABLE
            )
        ):
            raise InvalidExternalTaskTransitionError(
                "Permanent failure cannot be retried"
            )
        task.retry_count += 1
        self._transition(task, ExternalTaskStatus.QUEUED)
        self._emit(EventType.EXTERNAL_TASK_RETRY_REQUESTED, task, {"retry_count": task.retry_count})
        return task

    @atomic_domain_operation
    def approve_task(self, task_id, approver_id, reason=""):
        task = self.get_task(task_id)
        if task.status != ExternalTaskStatus.WAITING_FOR_REVIEW:
            raise ApprovalPolicyError("Approval requires review")
        if approver_id == task.provider_id:
            raise ApprovalPolicyError("Provider cannot approve its own work")
        item = decision(task_id, ApprovalStatus.APPROVED, approver_id, reason)
        self._decisions.setdefault(task_id, []).append(item)
        task.approval_status = ApprovalStatus.APPROVED
        self._transition(task, ExternalTaskStatus.APPROVED)
        self._emit(EventType.EXTERNAL_TASK_APPROVED, task, {"approver_id": approver_id})
        return item

    @atomic_domain_operation
    def reject_task(self, task_id, approver_id, reason):
        return self._review_decision(task_id, approver_id, reason, ApprovalStatus.REJECTED, ExternalTaskStatus.REJECTED, EventType.EXTERNAL_TASK_REJECTED)

    @atomic_domain_operation
    def request_changes(self, task_id, approver_id, reason):
        return self._review_decision(task_id, approver_id, reason, ApprovalStatus.CHANGES_REQUESTED, ExternalTaskStatus.CHANGES_REQUESTED, EventType.EXTERNAL_TASK_CHANGES_REQUESTED)

    @atomic_domain_operation
    def complete_task(self, task_id):
        task = self.get_task(task_id)
        self._transition(task, ExternalTaskStatus.COMPLETED)
        task.completed_at = datetime.now(timezone.utc)
        self._emit(EventType.EXTERNAL_TASK_COMPLETED, task, {"status": task.status.value})
        return task

    @atomic_domain_operation
    def cancel_task(self, task_id):
        task = self.get_task(task_id)
        if task.provider_id and task.status == ExternalTaskStatus.RUNNING:
            pass
        self._transition(task, ExternalTaskStatus.CANCELLED)
        self._emit(EventType.EXTERNAL_TASK_CANCELLED, task, {"status": task.status.value})
        return task

    def get_task(self, task_id):
        try: return self._tasks[task_id]
        except KeyError as error: raise ExternalTaskNotFoundError(task_id) from error

    def list_tasks(self): return tuple(self._tasks.values())
    def list_progress(self, task_id): return tuple(self._progress.get(task_id, ()))
    def get_result(self, task_id): return self._results.get(task_id)
    def list_decisions(self, task_id): return tuple(self._decisions.get(task_id, ()))
    def list_operations(self, task_id=None):
        values = self._operations.values()
        return tuple(item for item in values if task_id is None or item.task_id == task_id)

    def snapshot(self):
        return {
            "tasks": [self._serialize_task(item) for item in self._tasks.values()],
            "operations": [self._serialize_operation(item) for item in self._operations.values()],
            "decisions": [
                {"task_id": item.task_id, "decision": item.decision.value, "approver_id": item.approver_id, "reason": item.reason, "decided_at": item.decided_at.isoformat()}
                for values in self._decisions.values() for item in values
            ],
            "progress": {
                task_id: [
                    {
                        "task_id": item.task_id, "sequence": item.sequence,
                        "stage": item.stage, "message": item.message,
                        "timestamp": item.timestamp.isoformat(),
                        "artifact_references": list(item.artifact_references),
                    }
                    for item in values
                ]
                for task_id, values in self._progress.items()
            },
            "results": {
                task_id: {
                    "task_id": item.task_id,
                    "provider_task_id": item.provider_task_id,
                    "status": item.status.value, "summary": item.summary,
                    "changed_paths": list(item.changed_paths),
                    "commit_sha": item.commit_sha,
                    "test_results": list(item.test_results),
                    "generated_artifacts": list(item.generated_artifacts),
                    "failure_code": item.failure_code,
                    "started_at": item.started_at.isoformat(),
                    "completed_at": item.completed_at.isoformat(),
                }
                for task_id, item in self._results.items()
            },
        }

    def restore(self, snapshot):
        self._tasks = {
            value["task_id"]: self._deserialize_task(value)
            for value in snapshot.get("tasks", ())
        }
        self._operations = {}
        for value in snapshot.get("operations", ()):
            operation = ExternalOperation(
                value["operation_id"], value["task_id"], value["operation_type"],
                ExternalOperationStatus(value["status"]),
                datetime.fromisoformat(value["created_at"]),
                datetime.fromisoformat(value["updated_at"]),
                value["attempt"], value["failure_code"],
            )
            if operation.status == ExternalOperationStatus.STARTED:
                operation.status = ExternalOperationStatus.RECONCILIATION_REQUIRED
                self._tasks[operation.task_id].status = ExternalTaskStatus.RECONCILIATION_REQUIRED
            self._operations[operation.operation_id] = operation
        self._decisions = {}
        for value in snapshot.get("decisions", ()):
            item = decision(
                value["task_id"], ApprovalStatus(value["decision"]),
                value["approver_id"], value["reason"],
            )
            item = type(item)(
                item.task_id, item.decision, item.approver_id, item.reason,
                datetime.fromisoformat(value["decided_at"]),
            )
            self._decisions.setdefault(item.task_id, []).append(item)
        from runtime.coding_agents.models import (
            CodingAgentProgress,
            CodingAgentResultStatus,
            CodingAgentTaskResult,
        )
        self._progress = {
            task_id: [
                CodingAgentProgress(
                    value["task_id"], value["sequence"], value["stage"],
                    value["message"], datetime.fromisoformat(value["timestamp"]),
                    tuple(value["artifact_references"]),
                )
                for value in values
            ]
            for task_id, values in snapshot.get("progress", {}).items()
        }
        self._results = {
            task_id: CodingAgentTaskResult(
                value["task_id"], value["provider_task_id"],
                CodingAgentResultStatus(value["status"]), value["summary"],
                tuple(value["changed_paths"]), value["commit_sha"],
                tuple(value["test_results"]), tuple(value["generated_artifacts"]),
                value["failure_code"], datetime.fromisoformat(value["started_at"]),
                datetime.fromisoformat(value["completed_at"]),
            )
            for task_id, value in snapshot.get("results", {}).items()
        }

    def _review_decision(self, task_id, approver_id, reason, approval, status, event):
        task = self.get_task(task_id)
        if task.status != ExternalTaskStatus.WAITING_FOR_REVIEW:
            raise ApprovalPolicyError("Decision requires review")
        item = decision(task_id, approval, approver_id, reason)
        self._decisions.setdefault(task_id, []).append(item)
        task.approval_status = approval
        self._transition(task, status)
        self._emit(event, task, {"approver_id": approver_id, "reason": reason})
        return item

    def _transition(self, task, status):
        if status not in ALLOWED_TRANSITIONS.get(task.status, set()):
            raise InvalidExternalTaskTransitionError(f"{task.status.value} cannot become {status.value}")
        task.status = status

    def _operation(self, task, kind):
        now = datetime.now(timezone.utc)
        operation = ExternalOperation(str(uuid4()), task.task_id, kind, ExternalOperationStatus.PLANNED, now, now)
        self._operations[operation.operation_id] = operation
        return operation

    def _emit(self, event, task, payload):
        if self.event_publisher:
            self.event_publisher.publish(event, "external-task", task.task_id, payload, correlation_id=task.correlation_id, causation_id=task.causation_id)

    def _atomic(self):
        return (
            self.event_publisher.atomic()
            if self.event_publisher is not None
            else nullcontext()
        )

    @staticmethod
    def _validate_provider_progress(task_id, progress):
        for expected, item in enumerate(progress, start=1):
            if item.task_id != task_id or item.sequence != expected:
                raise ValueError("Provider progress sequence is invalid")

    @staticmethod
    def _serialize_task(item):
        value = dict(vars(item))
        for key in ("status", "approval_status"): value[key] = value[key].value
        for key in ("created_at", "started_at", "completed_at"):
            value[key] = value[key].isoformat() if value[key] else None
        return value

    @staticmethod
    def _deserialize_task(value):
        copied = dict(value)
        copied["status"] = ExternalTaskStatus(copied["status"])
        copied["approval_status"] = ApprovalStatus(copied["approval_status"])
        copied["requested_capabilities"] = tuple(copied["requested_capabilities"])
        for key in ("created_at", "started_at", "completed_at"):
            copied[key] = datetime.fromisoformat(copied[key]) if copied[key] else None
        return ExternalTask(**copied)

    @staticmethod
    def _serialize_operation(item):
        return {
            "operation_id": item.operation_id, "task_id": item.task_id,
            "operation_type": item.operation_type, "status": item.status.value,
            "created_at": item.created_at.isoformat(), "updated_at": item.updated_at.isoformat(),
            "attempt": item.attempt, "failure_code": item.failure_code,
        }
