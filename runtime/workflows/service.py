"""Service coordinating the complete deterministic software factory."""

from __future__ import annotations

from typing import TYPE_CHECKING, Literal

from runtime.agents.registry import AgentRegistry
from runtime.engine.runtime_engine import RuntimeEngine
from runtime.events.types import EventType
from runtime.exceptions import (
    DuplicateWorkflowError,
    ExecutionFailedError,
    InvalidWorkflowTransitionError,
    ValidationError,
    WorkflowApprovalError,
    WorkflowExecutionError,
    WorkflowNotFoundError,
    WorkflowReleaseError,
)
from runtime.execution.recovery import ExecutionRecoveryService
from runtime.execution.registry import ExecutorRegistry
from runtime.execution.service import ExecutionService
from runtime.models.lifecycle import LifecycleState
from runtime.orchestration.orchestrator import Orchestrator
from runtime.transactions import atomic_domain_operation
from runtime.validation import validate_required_string
from runtime.workflows.models import (
    SoftwareDeliveryRequest,
    SoftwareDeliveryWorkflow,
    WorkflowStage,
)
from runtime.workflows.policy import (
    require_approval_stage,
    require_cancellable,
    require_recoverable,
    require_release_stage,
    require_stage,
)

if TYPE_CHECKING:
    from runtime.events.event import RuntimeEvent
    from runtime.events.publisher import EventPublisher


class SoftwareDeliveryWorkflowService:
    """Compose existing runtime services into one auditable delivery flow."""

    def __init__(
        self,
        runtime_engine: RuntimeEngine,
        agent_registry: AgentRegistry,
        orchestrator: Orchestrator,
        executor_registry: ExecutorRegistry,
        execution_service: ExecutionService,
        execution_recovery_service: ExecutionRecoveryService,
        event_publisher: EventPublisher | None = None,
    ) -> None:
        expected = (
            (runtime_engine, RuntimeEngine, "runtime_engine"),
            (agent_registry, AgentRegistry, "agent_registry"),
            (orchestrator, Orchestrator, "orchestrator"),
            (executor_registry, ExecutorRegistry, "executor_registry"),
            (execution_service, ExecutionService, "execution_service"),
            (
                execution_recovery_service,
                ExecutionRecoveryService,
                "execution_recovery_service",
            ),
        )
        for value, value_type, name in expected:
            if not isinstance(value, value_type):
                raise ValidationError(f"{name} has an invalid type")
        self.runtime_engine = runtime_engine
        self.agent_registry = agent_registry
        self.orchestrator = orchestrator
        self.executor_registry = executor_registry
        self.execution_service = execution_service
        self.execution_recovery_service = execution_recovery_service
        self.event_publisher = event_publisher
        self._workflows: dict[str, SoftwareDeliveryWorkflow] = {}
        self._requests: dict[str, SoftwareDeliveryRequest] = {}
        if event_publisher is not None:
            event_publisher.register_snapshot_provider(self._snapshot_targets)

    @atomic_domain_operation
    def submit_request(
        self,
        request: SoftwareDeliveryRequest,
        *,
        workflow_id: str | None = None,
    ) -> SoftwareDeliveryWorkflow:
        if not isinstance(request, SoftwareDeliveryRequest):
            raise ValidationError(
                "request must be a SoftwareDeliveryRequest value"
            )
        resolved_id = workflow_id or request.id
        validate_required_string(resolved_id, "workflow_id")
        if resolved_id in self._workflows or request.id in self._requests:
            raise DuplicateWorkflowError(
                f"Workflow or request {resolved_id!r} already exists"
            )
        workflow = SoftwareDeliveryWorkflow(
            id=resolved_id,
            request_id=request.id,
            work_package_id=f"{resolved_id}:package",
            work_item_id=f"{resolved_id}:work-item",
            assignment_id=f"{resolved_id}:assignment",
        )
        self._workflows[workflow.id] = workflow
        self._requests[request.id] = request
        self.runtime_engine.create_work_package(
            workflow.work_package_id,
            request.title,
            request.description,
            request.requested_by,
        )
        self.runtime_engine.add_work_item(
            workflow.work_package_id,
            workflow.work_item_id,
            request.title,
            request.description,
            request.priority,
        )
        self._publish(
            workflow,
            EventType.SOFTWARE_REQUEST_SUBMITTED,
            {
                "request_id": request.id,
                "requested_by": request.requested_by,
            },
        )
        return workflow

    @atomic_domain_operation
    def plan_request(self, workflow_id: str) -> SoftwareDeliveryWorkflow:
        workflow = self.get_workflow(workflow_id)
        require_stage(workflow.current_stage, WorkflowStage.INTAKE)
        request = self._requests[workflow.request_id]
        workflow.move_to(WorkflowStage.PLANNING)
        self.runtime_engine.change_work_item_state(
            workflow.work_package_id,
            workflow.work_item_id,
            LifecycleState.READY,
        )
        workflow.move_to(WorkflowStage.READY)
        self._publish(
            workflow,
            EventType.SOFTWARE_REQUEST_PLANNED,
            {"acceptance_criteria": request.acceptance_criteria},
        )
        return workflow

    @atomic_domain_operation
    def prepare_work(self, workflow_id: str) -> SoftwareDeliveryWorkflow:
        workflow = self.get_workflow(workflow_id)
        if workflow.current_stage == WorkflowStage.READY:
            return workflow
        require_stage(workflow.current_stage, WorkflowStage.PLANNING)
        self.runtime_engine.change_work_item_state(
            workflow.work_package_id,
            workflow.work_item_id,
            LifecycleState.READY,
        )
        workflow.move_to(WorkflowStage.READY)
        return workflow

    @atomic_domain_operation
    def assign_work(self, workflow_id: str) -> SoftwareDeliveryWorkflow:
        workflow = self.get_workflow(workflow_id)
        require_stage(workflow.current_stage, WorkflowStage.READY)
        request = self._requests[workflow.request_id]
        assignment = self.orchestrator.assign_work_item(
            workflow.assignment_id,
            workflow.work_package_id,
            workflow.work_item_id,
            request.required_role,
            list(request.required_capabilities),
        )
        workflow.move_to(WorkflowStage.ASSIGNED)
        self._publish(
            workflow,
            EventType.SOFTWARE_WORK_ASSIGNED,
            {"agent_id": assignment.agent_id},
        )
        return workflow

    @atomic_domain_operation
    def execute_work(
        self,
        workflow_id: str,
        execution_id: str | None = None,
    ) -> SoftwareDeliveryWorkflow:
        workflow = self.get_workflow(workflow_id)
        if workflow.current_stage not in {
            WorkflowStage.ASSIGNED,
            WorkflowStage.EXECUTING,
        }:
            raise InvalidWorkflowTransitionError(
                "Execution requires ASSIGNED or correction-stage EXECUTING"
            )
        resolved_id = execution_id or (
            f"{workflow.id}:execution:{len(workflow.execution_ids) + 1}"
        )
        validate_required_string(resolved_id, "execution_id")
        if workflow.current_stage == WorkflowStage.ASSIGNED:
            workflow.move_to(WorkflowStage.EXECUTING)
        self._publish(
            workflow,
            EventType.SOFTWARE_EXECUTION_STARTED,
            {"execution_id": resolved_id},
        )
        try:
            execution = self.execution_service.execute_assignment(
                resolved_id,
                workflow.assignment_id,
                {
                    "correlation_id": self._correlation_id(workflow),
                    "causation_id": self._last_event_id(workflow),
                },
            )
        except ExecutionFailedError as error:
            if resolved_id not in workflow.execution_ids:
                workflow.execution_ids.append(resolved_id)
            workflow.failure_reason = str(error)
            workflow.move_to(WorkflowStage.FAILED)
            self._publish(
                workflow,
                EventType.SOFTWARE_EXECUTION_FAILED,
                {
                    "execution_id": resolved_id,
                    "reason": workflow.failure_reason,
                },
            )
            raise WorkflowExecutionError(workflow.failure_reason) from error
        workflow.execution_ids.append(execution.id)
        workflow.failure_reason = None
        workflow.move_to(WorkflowStage.REVIEW)
        self._publish(
            workflow,
            EventType.SOFTWARE_EXECUTION_SUCCEEDED,
            {"execution_id": execution.id},
        )
        self._publish(
            workflow,
            EventType.SOFTWARE_REVIEW_SUBMITTED,
            {"execution_id": execution.id},
        )
        return workflow

    def submit_for_review(
        self,
        workflow_id: str,
    ) -> SoftwareDeliveryWorkflow:
        workflow = self.get_workflow(workflow_id)
        require_stage(workflow.current_stage, WorkflowStage.REVIEW)
        return workflow

    @atomic_domain_operation
    def approve_work(self, workflow_id: str) -> SoftwareDeliveryWorkflow:
        workflow = self.get_workflow(workflow_id)
        require_approval_stage(workflow.current_stage)
        item = self.runtime_engine.get_work_item(
            workflow.work_package_id,
            workflow.work_item_id,
        )
        if item.lifecycle_state != LifecycleState.REVIEW:
            raise WorkflowApprovalError(
                "Approval requires work item state REVIEW"
            )
        self.runtime_engine.change_work_item_state(
            workflow.work_package_id,
            workflow.work_item_id,
            LifecycleState.APPROVED,
        )
        workflow.move_to(WorkflowStage.APPROVAL)
        self._publish(workflow, EventType.SOFTWARE_WORK_APPROVED, {})
        return workflow

    @atomic_domain_operation
    def reject_work(self, workflow_id: str) -> SoftwareDeliveryWorkflow:
        workflow = self.get_workflow(workflow_id)
        require_stage(workflow.current_stage, WorkflowStage.REVIEW)
        self.runtime_engine.change_work_item_state(
            workflow.work_package_id,
            workflow.work_item_id,
            LifecycleState.REJECTED,
        )
        workflow.move_to(WorkflowStage.EXECUTING)
        self._publish(workflow, EventType.SOFTWARE_WORK_REJECTED, {})
        return workflow

    @atomic_domain_operation
    def complete_work(self, workflow_id: str) -> SoftwareDeliveryWorkflow:
        workflow = self.get_workflow(workflow_id)
        require_stage(workflow.current_stage, WorkflowStage.APPROVAL)
        item = self.runtime_engine.get_work_item(
            workflow.work_package_id,
            workflow.work_item_id,
        )
        if item.lifecycle_state != LifecycleState.APPROVED:
            raise WorkflowApprovalError(
                "Completion requires work item state APPROVED"
            )
        self.orchestrator.complete_assignment(workflow.assignment_id)
        workflow.move_to(WorkflowStage.COMPLETED)
        self._publish(workflow, EventType.SOFTWARE_WORK_COMPLETED, {})
        return workflow

    @atomic_domain_operation
    def release_work(self, workflow_id: str) -> SoftwareDeliveryWorkflow:
        workflow = self.get_workflow(workflow_id)
        require_release_stage(workflow.current_stage)
        item = self.runtime_engine.get_work_item(
            workflow.work_package_id,
            workflow.work_item_id,
        )
        if item.lifecycle_state != LifecycleState.COMPLETED:
            raise WorkflowReleaseError(
                "Release requires work item state COMPLETED"
            )
        self.runtime_engine.change_work_item_state(
            workflow.work_package_id,
            workflow.work_item_id,
            LifecycleState.RELEASED,
        )
        workflow.move_to(WorkflowStage.RELEASED)
        self._publish(workflow, EventType.SOFTWARE_WORK_RELEASED, {})
        return workflow

    @atomic_domain_operation
    def cancel_workflow(
        self,
        workflow_id: str,
        reason: str = "Workflow cancelled",
    ) -> SoftwareDeliveryWorkflow:
        validate_required_string(reason, "reason")
        workflow = self.get_workflow(workflow_id)
        require_cancellable(workflow.current_stage)
        if workflow.current_stage == WorkflowStage.ASSIGNED:
            self.orchestrator.cancel_assignment(workflow.assignment_id)
        elif workflow.current_stage == WorkflowStage.FAILED:
            self.execution_recovery_service.cancel_failed_assignment(
                f"{workflow.id}:cancellation",
                workflow.execution_ids[-1],
                reason,
            )
        workflow.move_to(WorkflowStage.CANCELLED)
        workflow.failure_reason = reason
        self._publish(
            workflow,
            EventType.SOFTWARE_WORKFLOW_CANCELLED,
            {"reason": reason},
        )
        return workflow

    @atomic_domain_operation
    def recover_failed_execution(
        self,
        workflow_id: str,
        recovery_id: str,
        reason: str,
        *,
        action: Literal["retry", "reset", "cancel"] = "retry",
        new_execution_id: str | None = None,
    ) -> SoftwareDeliveryWorkflow:
        workflow = self.get_workflow(workflow_id)
        require_recoverable(workflow.current_stage)
        failed_execution_id = workflow.execution_ids[-1]
        if action == "retry":
            resolved_execution_id = new_execution_id or (
                f"{workflow.id}:execution:{len(workflow.execution_ids) + 1}"
            )
            try:
                execution = (
                    self.execution_recovery_service.retry_failed_execution(
                        recovery_id,
                        failed_execution_id,
                        resolved_execution_id,
                        reason,
                        {
                            "correlation_id": self._correlation_id(workflow),
                            "causation_id": self._last_event_id(workflow),
                        },
                    )
                )
            except ExecutionFailedError as error:
                workflow.execution_ids.append(resolved_execution_id)
                workflow.failure_reason = str(error)
                self._publish(
                    workflow,
                    EventType.SOFTWARE_EXECUTION_FAILED,
                    {
                        "execution_id": resolved_execution_id,
                        "reason": workflow.failure_reason,
                    },
                )
                raise WorkflowExecutionError(str(error)) from error
            workflow.execution_ids.append(execution.id)
            workflow.failure_reason = None
            workflow.move_to(WorkflowStage.REVIEW)
        elif action == "reset":
            self.execution_recovery_service.reset_failed_execution(
                recovery_id,
                failed_execution_id,
                reason,
            )
            workflow.failure_reason = None
            workflow.move_to(WorkflowStage.ASSIGNED)
        elif action == "cancel":
            self.execution_recovery_service.cancel_failed_assignment(
                recovery_id,
                failed_execution_id,
                reason,
            )
            workflow.move_to(WorkflowStage.CANCELLED)
        else:
            raise ValidationError(
                "recovery action must be retry, reset, or cancel"
            )
        self._publish(
            workflow,
            EventType.SOFTWARE_EXECUTION_RECOVERED,
            {
                "action": action,
                "execution_id": failed_execution_id,
                "new_execution_id": (
                    resolved_execution_id if action == "retry" else None
                ),
            },
        )
        if action == "cancel":
            self._publish(
                workflow,
                EventType.SOFTWARE_WORKFLOW_CANCELLED,
                {"reason": reason},
            )
        return workflow

    def get_workflow(self, workflow_id: str) -> SoftwareDeliveryWorkflow:
        validate_required_string(workflow_id, "workflow_id")
        if workflow_id not in self._workflows:
            raise WorkflowNotFoundError(
                f"Workflow {workflow_id!r} was not found"
            )
        return self._workflows[workflow_id]

    def list_workflows(self) -> list[SoftwareDeliveryWorkflow]:
        return list(self._workflows.values())

    def get_workflow_events(
        self,
        workflow_id: str,
    ) -> list[RuntimeEvent]:
        workflow = self.get_workflow(workflow_id)
        if self.event_publisher is None:
            return []
        return self.event_publisher.event_store.list_events_for_correlation(
            self._correlation_id(workflow)
        )

    def _correlation_id(self, workflow: SoftwareDeliveryWorkflow) -> str:
        request = self._requests[workflow.request_id]
        return request.correlation_id or workflow.id

    def _last_event_id(
        self,
        workflow: SoftwareDeliveryWorkflow,
    ) -> str | None:
        if self.event_publisher is None:
            return None
        correlation_id = self._correlation_id(workflow)
        events = self.get_workflow_events(workflow.id)
        transaction = self.event_publisher.transactions.current
        if transaction is not None:
            events.extend(
                event
                for event in transaction.staged_events
                if event.correlation_id == correlation_id
            )
        return events[-1].id if events else None

    def _publish(
        self,
        workflow: SoftwareDeliveryWorkflow,
        event_type: EventType,
        payload: dict[str, object],
    ) -> RuntimeEvent | None:
        if self.event_publisher is None:
            return None
        return self.event_publisher.publish(
            event_type,
            "SOFTWARE_DELIVERY_WORKFLOW",
            workflow.id,
            {
                "stage": workflow.current_stage.value,
                **payload,
            },
            correlation_id=self._correlation_id(workflow),
            causation_id=self._last_event_id(workflow),
        )

    def _snapshot_targets(self) -> list[object]:
        targets: list[object] = [self._workflows, self._requests]
        for workflow in self._workflows.values():
            targets.extend([workflow, workflow.execution_ids])
        return targets
