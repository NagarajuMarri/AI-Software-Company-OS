"""Explicit policies for software delivery workflow decisions."""

from runtime.exceptions import (
    InvalidWorkflowTransitionError,
    WorkflowApprovalError,
    WorkflowReleaseError,
)
from runtime.workflows.models import WorkflowStage


ALLOWED_STAGE_TRANSITIONS = {
    WorkflowStage.INTAKE: frozenset(
        {WorkflowStage.PLANNING, WorkflowStage.CANCELLED}
    ),
    WorkflowStage.PLANNING: frozenset(
        {WorkflowStage.READY, WorkflowStage.CANCELLED}
    ),
    WorkflowStage.READY: frozenset(
        {WorkflowStage.ASSIGNED, WorkflowStage.CANCELLED}
    ),
    WorkflowStage.ASSIGNED: frozenset(
        {
            WorkflowStage.EXECUTING,
            WorkflowStage.CANCELLED,
        }
    ),
    WorkflowStage.EXECUTING: frozenset(
        {
            WorkflowStage.REVIEW,
            WorkflowStage.FAILED,
            WorkflowStage.CANCELLED,
        }
    ),
    WorkflowStage.REVIEW: frozenset(
        {
            WorkflowStage.APPROVAL,
            WorkflowStage.EXECUTING,
        }
    ),
    WorkflowStage.APPROVAL: frozenset({WorkflowStage.COMPLETED}),
    WorkflowStage.COMPLETED: frozenset({WorkflowStage.RELEASED}),
    WorkflowStage.RELEASED: frozenset(),
    WorkflowStage.FAILED: frozenset(
        {
            WorkflowStage.ASSIGNED,
            WorkflowStage.REVIEW,
            WorkflowStage.FAILED,
            WorkflowStage.CANCELLED,
        }
    ),
    WorkflowStage.CANCELLED: frozenset(),
}

CANCELLABLE_STAGES = frozenset(
    {
        WorkflowStage.INTAKE,
        WorkflowStage.PLANNING,
        WorkflowStage.READY,
        WorkflowStage.ASSIGNED,
        WorkflowStage.FAILED,
    }
)


def require_stage_transition(
    current: WorkflowStage,
    target: WorkflowStage,
) -> None:
    if target not in ALLOWED_STAGE_TRANSITIONS[current]:
        raise InvalidWorkflowTransitionError(
            f"Cannot transition workflow from {current.value} to {target.value}"
        )


def require_stage(
    current: WorkflowStage,
    expected: WorkflowStage,
) -> None:
    if current != expected:
        raise InvalidWorkflowTransitionError(
            f"Operation requires workflow stage {expected.value}; "
            f"received {current.value}"
        )


def require_approval_stage(current: WorkflowStage) -> None:
    if current != WorkflowStage.REVIEW:
        raise WorkflowApprovalError(
            "Approval requires workflow stage REVIEW"
        )


def require_release_stage(current: WorkflowStage) -> None:
    if current != WorkflowStage.COMPLETED:
        raise WorkflowReleaseError(
            "Release requires workflow stage COMPLETED"
        )


def require_cancellable(current: WorkflowStage) -> None:
    if current not in CANCELLABLE_STAGES:
        raise InvalidWorkflowTransitionError(
            f"Workflow cannot be cancelled from {current.value}"
        )


def require_recoverable(current: WorkflowStage) -> None:
    if current != WorkflowStage.FAILED:
        raise InvalidWorkflowTransitionError(
            "Execution recovery requires workflow stage FAILED"
        )
