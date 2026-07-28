"""Deterministic coordinator for runtime work and registered agents."""

from __future__ import annotations

from typing import TYPE_CHECKING

from runtime.agents.metadata import AgentMetadata
from runtime.agents.registry import AgentRegistry
from runtime.agents.role import AgentRole
from runtime.agents.state import AgentState
from runtime.engine.runtime_engine import RuntimeEngine
from runtime.exceptions import (
    AgentCapacityError,
    AssignmentNotFoundError,
    DuplicateActiveAssignmentError,
    InvalidAssignmentStateTransitionError,
    NoEligibleAgentError,
    ValidationError,
)
from runtime.models.lifecycle import LifecycleState
from runtime.orchestration.assignment import AssignmentStatus, WorkAssignment
from runtime.orchestration.selection import (
    AgentSelectionResult,
    validate_optional_role,
    validate_required_capabilities,
)
from runtime.validation import validate_required_string

if TYPE_CHECKING:
    from runtime.events.publisher import EventPublisher


class Orchestrator:
    """Coordinate deterministic assignment without execution or queues."""

    def __init__(
        self,
        runtime_engine: RuntimeEngine,
        agent_registry: AgentRegistry,
        event_publisher: EventPublisher | None = None,
    ) -> None:
        if not isinstance(runtime_engine, RuntimeEngine):
            raise ValidationError("runtime_engine must be a RuntimeEngine value")
        if not isinstance(agent_registry, AgentRegistry):
            raise ValidationError("agent_registry must be an AgentRegistry value")
        self.runtime_engine = runtime_engine
        self.agent_registry = agent_registry
        self.event_publisher = event_publisher
        self._assignments: dict[str, WorkAssignment] = {}

    def select_agent(
        self,
        required_role: AgentRole | None = None,
        required_capabilities: list[str] | None = None,
    ) -> AgentSelectionResult:
        """Select the highest-ranked eligible agent deterministically."""
        validate_optional_role(required_role)
        capability_ids = validate_required_capabilities(
            [] if required_capabilities is None else required_capabilities
        )

        ranked: list[tuple[int, int, int, int, AgentMetadata]] = []
        capacity_blocked = False
        for registration_index, agent in enumerate(
            self.agent_registry.list_agents()
        ):
            if required_role is not None and agent.role != required_role:
                continue
            if not all(
                agent.supports_capability(capability_id)
                for capability_id in capability_ids
            ):
                continue

            active_count = self._count_active_assignments(agent.id)
            if active_count >= agent.max_parallel_tasks:
                capacity_blocked = True
                continue
            if agent.state != AgentState.AVAILABLE:
                continue

            ranked.append(
                (
                    -len(capability_ids),
                    -agent.priority,
                    active_count,
                    registration_index,
                    agent,
                )
            )

        if not ranked:
            if capacity_blocked:
                raise AgentCapacityError(
                    "Matching agents have reached max_parallel_tasks capacity"
                )
            raise NoEligibleAgentError("No eligible available agent was found")

        _, _, active_count, _, selected = min(ranked)
        return AgentSelectionResult(
            agent=selected,
            score=len(capability_ids),
            matched_capabilities=capability_ids,
            reason=(
                f"Matched {len(capability_ids)} required capabilities; "
                f"priority {selected.priority}; "
                f"{active_count} active assignments"
            ),
        )

    def assign_work_item(
        self,
        assignment_id: str,
        package_id: str,
        work_item_id: str,
        required_role: AgentRole | None = None,
        required_capabilities: list[str] | None = None,
    ) -> WorkAssignment:
        """Select an agent and activate an assignment for a READY work item."""
        validate_required_string(assignment_id, "assignment_id")
        validate_required_string(package_id, "package_id")
        validate_required_string(work_item_id, "work_item_id")
        if assignment_id in self._assignments:
            raise ValidationError(
                f"Assignment {assignment_id!r} already exists"
            )

        work_item = self.runtime_engine.get_work_item(package_id, work_item_id)
        if any(
            assignment.package_id == package_id
            and assignment.work_item_id == work_item_id
            and assignment.status == AssignmentStatus.ACTIVE
            for assignment in self._assignments.values()
        ):
            raise DuplicateActiveAssignmentError(
                f"Work item {work_item_id!r} already has an active assignment"
            )
        if work_item.lifecycle_state != LifecycleState.READY:
            raise InvalidAssignmentStateTransitionError(
                "Work item must be READY before assignment"
            )

        result = self.select_agent(required_role, required_capabilities)
        active_after_assignment = self._count_active_assignments(
            result.agent.id
        ) + 1
        assignment = WorkAssignment(
            id=assignment_id,
            package_id=package_id,
            work_item_id=work_item_id,
            agent_id=result.agent.id,
            required_role=required_role,
            required_capabilities=(
                [] if required_capabilities is None else required_capabilities
            ),
            selection_reason=result.reason,
            selected_agent_priority=result.agent.priority,
            selected_agent_active_assignment_count=active_after_assignment - 1,
        )
        assignment.change_status(AssignmentStatus.ACTIVE)

        package = self.runtime_engine.get_work_package(package_id)
        work_item_state = work_item.lifecycle_state
        assigned_to = work_item.assigned_to
        agent_state = result.agent.state
        package_updated_at = package.updated_at
        try:
            self.runtime_engine.change_work_item_state(
                package_id,
                work_item_id,
                LifecycleState.ASSIGNED,
            )
            work_item.assigned_to = result.agent.id
            if active_after_assignment == result.agent.max_parallel_tasks:
                self.agent_registry.update_agent_state(
                    result.agent.id,
                    AgentState.BUSY,
                )
            self._assignments[assignment.id] = assignment
        except Exception:
            work_item.lifecycle_state = work_item_state
            work_item.assigned_to = assigned_to
            result.agent.state = agent_state
            package.updated_at = package_updated_at
            self._assignments.pop(assignment.id, None)
            raise
        self._publish(
            "ASSIGNMENT_CREATED",
            assignment,
            {
                "package_id": package_id,
                "work_item_id": work_item_id,
                "agent_id": assignment.agent_id,
            },
        )
        return assignment

    def complete_assignment(self, assignment_id: str) -> WorkAssignment:
        """Complete active work after review/approval and release capacity."""
        assignment = self.get_assignment(assignment_id)
        self._require_active(assignment)
        work_item = self.runtime_engine.get_work_item(
            assignment.package_id,
            assignment.work_item_id,
        )
        if work_item.lifecycle_state != LifecycleState.APPROVED:
            raise InvalidAssignmentStateTransitionError(
                "Assignment completion requires work item APPROVED"
            )

        package = self.runtime_engine.get_work_package(assignment.package_id)
        agent = self.agent_registry.get_agent(assignment.agent_id)
        work_item_state = work_item.lifecycle_state
        agent_state = agent.state
        assignment_status = assignment.status
        assignment_updated_at = assignment.updated_at
        package_updated_at = package.updated_at
        try:
            self.runtime_engine.change_work_item_state(
                assignment.package_id,
                assignment.work_item_id,
                LifecycleState.COMPLETED,
            )
            assignment.change_status(AssignmentStatus.COMPLETED)
            self._release_agent_capacity(assignment.agent_id)
        except Exception:
            work_item.lifecycle_state = work_item_state
            agent.state = agent_state
            assignment.status = assignment_status
            assignment.updated_at = assignment_updated_at
            package.updated_at = package_updated_at
            raise
        self._publish(
            "ASSIGNMENT_COMPLETED",
            assignment,
            {"work_item_id": assignment.work_item_id},
        )
        return assignment

    def cancel_assignment(self, assignment_id: str) -> WorkAssignment:
        """Cancel active pre-execution work and return it to READY."""
        assignment = self.get_assignment(assignment_id)
        self._require_active(assignment)
        work_item = self.runtime_engine.get_work_item(
            assignment.package_id,
            assignment.work_item_id,
        )
        if work_item.lifecycle_state != LifecycleState.ASSIGNED:
            raise InvalidAssignmentStateTransitionError(
                "Cancellation requires the work item to remain ASSIGNED"
            )
        package = self.runtime_engine.get_work_package(assignment.package_id)
        agent = self.agent_registry.get_agent(assignment.agent_id)
        work_item_state = work_item.lifecycle_state
        assigned_to = work_item.assigned_to
        agent_state = agent.state
        assignment_status = assignment.status
        assignment_updated_at = assignment.updated_at
        package_updated_at = package.updated_at
        try:
            self.runtime_engine.change_work_item_state(
                assignment.package_id,
                assignment.work_item_id,
                LifecycleState.READY,
            )
            work_item.assigned_to = None
            assignment.change_status(AssignmentStatus.CANCELLED)
            self._release_agent_capacity(assignment.agent_id)
        except Exception:
            work_item.lifecycle_state = work_item_state
            work_item.assigned_to = assigned_to
            agent.state = agent_state
            assignment.status = assignment_status
            assignment.updated_at = assignment_updated_at
            package.updated_at = package_updated_at
            raise
        self._publish(
            "ASSIGNMENT_CANCELLED",
            assignment,
            {"work_item_id": assignment.work_item_id},
        )
        return assignment

    def get_assignment(self, assignment_id: str) -> WorkAssignment:
        """Retrieve an assignment by identifier."""
        validate_required_string(assignment_id, "assignment_id")
        if assignment_id not in self._assignments:
            raise AssignmentNotFoundError(
                f"Assignment {assignment_id!r} was not found"
            )
        return self._assignments[assignment_id]

    def list_assignments(self) -> list[WorkAssignment]:
        """Return assignments in creation order."""
        return list(self._assignments.values())

    def list_assignments_for_agent(
        self,
        agent_id: str,
    ) -> list[WorkAssignment]:
        """Return assignments for a registered agent."""
        self.agent_registry.get_agent(agent_id)
        return [
            assignment
            for assignment in self._assignments.values()
            if assignment.agent_id == agent_id
        ]

    def list_assignments_for_work_item(
        self,
        package_id: str,
        work_item_id: str,
    ) -> list[WorkAssignment]:
        """Return assignment history for an existing work item."""
        validate_required_string(package_id, "package_id")
        validate_required_string(work_item_id, "work_item_id")
        self.runtime_engine.get_work_item(package_id, work_item_id)
        return [
            assignment
            for assignment in self._assignments.values()
            if assignment.package_id == package_id
            and assignment.work_item_id == work_item_id
        ]

    def get_active_assignment_count(self, agent_id: str) -> int:
        """Return the active assignment count for a registered agent."""
        self.agent_registry.get_agent(agent_id)
        return self._count_active_assignments(agent_id)

    def _count_active_assignments(self, agent_id: str) -> int:
        return sum(
            assignment.agent_id == agent_id
            and assignment.status == AssignmentStatus.ACTIVE
            for assignment in self._assignments.values()
        )

    @staticmethod
    def _require_active(assignment: WorkAssignment) -> None:
        if assignment.status != AssignmentStatus.ACTIVE:
            raise InvalidAssignmentStateTransitionError(
                "Assignment must be ACTIVE for this operation"
            )

    def _release_agent_capacity(self, agent_id: str) -> None:
        agent = self.agent_registry.get_agent(agent_id)
        if (
            agent.state == AgentState.BUSY
            and self._count_active_assignments(agent_id)
            < agent.max_parallel_tasks
        ):
            self.agent_registry.update_agent_state(
                agent_id,
                AgentState.AVAILABLE,
            )

    def _publish(
        self,
        event_name: str,
        assignment: WorkAssignment,
        payload: dict[str, object],
    ) -> None:
        if self.event_publisher is None:
            return
        from runtime.events.types import EventType

        self.event_publisher.publish(
            EventType(event_name),
            "ASSIGNMENT",
            assignment.id,
            payload,
        )
