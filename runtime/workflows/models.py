"""Models for deterministic software delivery workflows."""

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum

from runtime.agents.role import AgentRole, validate_agent_role
from runtime.exceptions import ValidationError
from runtime.validation import (
    validate_optional_string,
    validate_required_string,
)


class WorkflowStage(str, Enum):
    INTAKE = "INTAKE"
    PLANNING = "PLANNING"
    READY = "READY"
    ASSIGNED = "ASSIGNED"
    EXECUTING = "EXECUTING"
    REVIEW = "REVIEW"
    APPROVAL = "APPROVAL"
    COMPLETED = "COMPLETED"
    RELEASED = "RELEASED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


def _validate_utc(value: object, field_name: str) -> None:
    if (
        not isinstance(value, datetime)
        or value.tzinfo is None
        or value.utcoffset() != timedelta(0)
    ):
        raise ValidationError(f"{field_name} must be timezone-aware UTC")


def _validated_strings(
    values: tuple[str, ...] | list[str],
    field_name: str,
    *,
    allow_empty: bool = True,
) -> tuple[str, ...]:
    if not isinstance(values, (tuple, list)):
        raise ValidationError(f"{field_name} must be a list or tuple")
    resolved = tuple(values)
    if not allow_empty and not resolved:
        raise ValidationError(f"{field_name} must not be empty")
    for value in resolved:
        validate_required_string(value, field_name)
    if len(resolved) != len(set(resolved)):
        raise ValidationError(f"{field_name} must not contain duplicates")
    return resolved


@dataclass(frozen=True)
class SoftwareDeliveryRequest:
    id: str
    title: str
    description: str
    requested_by: str
    required_role: AgentRole
    required_capabilities: tuple[str, ...] | list[str]
    acceptance_criteria: tuple[str, ...] | list[str]
    priority: str = "normal"
    correlation_id: str | None = None
    created_at: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc)
    )

    def __post_init__(self) -> None:
        validate_required_string(self.id, "SoftwareDeliveryRequest.id")
        validate_required_string(self.title, "SoftwareDeliveryRequest.title")
        validate_required_string(
            self.description,
            "SoftwareDeliveryRequest.description",
        )
        validate_required_string(
            self.requested_by,
            "SoftwareDeliveryRequest.requested_by",
        )
        validate_agent_role(self.required_role)
        object.__setattr__(
            self,
            "required_capabilities",
            _validated_strings(
                self.required_capabilities,
                "SoftwareDeliveryRequest.required_capabilities",
            ),
        )
        object.__setattr__(
            self,
            "acceptance_criteria",
            _validated_strings(
                self.acceptance_criteria,
                "SoftwareDeliveryRequest.acceptance_criteria",
                allow_empty=False,
            ),
        )
        validate_required_string(
            self.priority,
            "SoftwareDeliveryRequest.priority",
        )
        validate_optional_string(
            self.correlation_id,
            "SoftwareDeliveryRequest.correlation_id",
        )
        _validate_utc(self.created_at, "SoftwareDeliveryRequest.created_at")


@dataclass
class SoftwareDeliveryWorkflow:
    id: str
    request_id: str
    work_package_id: str
    work_item_id: str
    assignment_id: str
    execution_ids: list[str] = field(default_factory=list)
    current_stage: WorkflowStage = WorkflowStage.INTAKE
    created_at: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    updated_at: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    failure_reason: str | None = None

    def __post_init__(self) -> None:
        for name in (
            "id",
            "request_id",
            "work_package_id",
            "work_item_id",
            "assignment_id",
        ):
            validate_required_string(
                getattr(self, name),
                f"SoftwareDeliveryWorkflow.{name}",
            )
        if not isinstance(self.current_stage, WorkflowStage):
            raise ValidationError(
                "SoftwareDeliveryWorkflow.current_stage must be a WorkflowStage"
            )
        self.execution_ids = list(
            _validated_strings(
                self.execution_ids,
                "SoftwareDeliveryWorkflow.execution_ids",
            )
        )
        validate_optional_string(
            self.failure_reason,
            "SoftwareDeliveryWorkflow.failure_reason",
        )
        _validate_utc(self.created_at, "SoftwareDeliveryWorkflow.created_at")
        _validate_utc(self.updated_at, "SoftwareDeliveryWorkflow.updated_at")

    def move_to(self, stage: WorkflowStage) -> None:
        from runtime.workflows.policy import require_stage_transition

        require_stage_transition(self.current_stage, stage)
        self.current_stage = stage
        self.updated_at = datetime.now(timezone.utc)
