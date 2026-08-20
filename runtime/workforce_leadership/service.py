"""Governed composition of Day 22 execution with Day 23 leadership outputs."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone
import hashlib
import json

from runtime.agents import AgentRole
from runtime.digital_twin import (
    ContextValue,
    DelegatedAuthority,
    DigitalTwinAssignment,
    DigitalTwinDefinition,
    DigitalTwinExecutionStatus,
    DigitalTwinRuntime,
    ProviderExecutionRequest,
)
from runtime.workforce_leadership.errors import LeadershipWorkforcePolicyError
from runtime.workforce_leadership.models import (
    ARTIFACT_STATUS,
    CEO_ACTION_IDS,
    CEO_CAPABILITY_IDS,
    LeadershipArtifact,
    LeadershipArtifactKind,
    LeadershipStatusReport,
    OpportunityIntake,
    PILOT_STATUS,
    PRODUCT_MANAGER_ACTION_IDS,
    PRODUCT_MANAGER_CAPABILITY_IDS,
    WORK_STATUS,
    artifact_id_for,
    validate_action_profile,
)
from runtime.workforce_leadership.persistence import FileLeadershipArtifactStore
from runtime.workforce_leadership.provider import LeadershipAgentProvider


def ceo_objective(intake: OpportunityIntake) -> str:
    """Return the exact non-approving CEO objective used by delegated authority."""

    if not isinstance(intake, OpportunityIntake):
        raise TypeError("CEO opportunity intake is invalid")
    return (
        f"Frame opportunity {intake.opportunity_id} as a draft brief and status report "
        "for human review; do not approve, fund, implement, or select a pilot product."
    )


def product_manager_objective(
    intake: OpportunityIntake,
    ceo_artifact: LeadershipArtifact,
) -> str:
    """Return the exact draft-only Product Manager objective."""

    if not isinstance(intake, OpportunityIntake) or not isinstance(
        ceo_artifact, LeadershipArtifact
    ):
        raise TypeError("Product Manager source is invalid")
    return (
        f"Clarify scope and propose a draft product plan for {intake.opportunity_id} "
        f"from CEO brief {ceo_artifact.artifact_id}; report status for human review "
        "without architecture, implementation, approval, or pilot selection."
    )


class LeadershipWorkforceService:
    """Execute exact CEO/PM role profiles and persist validated draft artifacts."""

    def __init__(
        self,
        runtime: DigitalTwinRuntime,
        provider: LeadershipAgentProvider,
        store: FileLeadershipArtifactStore,
        *,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        if not isinstance(runtime, DigitalTwinRuntime):
            raise TypeError("Leadership runtime must be a DigitalTwinRuntime")
        if not isinstance(provider, LeadershipAgentProvider):
            raise TypeError("Leadership provider is invalid")
        if not isinstance(store, FileLeadershipArtifactStore):
            raise TypeError("Leadership artifact store is invalid")
        self._runtime = runtime
        self._provider = provider
        self._store = store
        self._clock = clock or (lambda: datetime.now(timezone.utc))

    def run_ceo(
        self,
        *,
        execution_id: str,
        twin: DigitalTwinDefinition,
        authority: DelegatedAuthority,
        intake: OpportunityIntake,
    ) -> LeadershipArtifact:
        """Create or reopen one exact CEO opportunity brief and status report."""

        objective = ceo_objective(intake)
        self._validate_profile(
            intake,
            twin,
            authority,
            role=AgentRole.CEO,
            capability_ids=CEO_CAPABILITY_IDS,
            action_ids=CEO_ACTION_IDS,
            objective=objective,
        )
        assignment = self._assignment(
            intake,
            twin,
            authority,
            objective,
            CEO_CAPABILITY_IDS,
            upstream=None,
        )
        return self._execute(
            execution_id,
            twin,
            assignment,
            authority,
            intake,
            LeadershipArtifactKind.CEO_OPPORTUNITY_BRIEF,
            upstream=None,
        )

    def run_product_manager(
        self,
        *,
        execution_id: str,
        twin: DigitalTwinDefinition,
        authority: DelegatedAuthority,
        intake: OpportunityIntake,
        ceo_artifact: LeadershipArtifact,
    ) -> LeadershipArtifact:
        """Create or reopen one exact Product Manager scope/plan/status draft."""

        self._validate_ceo_handoff(intake, ceo_artifact)
        objective = product_manager_objective(intake, ceo_artifact)
        self._validate_profile(
            intake,
            twin,
            authority,
            role=AgentRole.PROJECT_MANAGER,
            capability_ids=PRODUCT_MANAGER_CAPABILITY_IDS,
            action_ids=PRODUCT_MANAGER_ACTION_IDS,
            objective=objective,
        )
        assignment = self._assignment(
            intake,
            twin,
            authority,
            objective,
            PRODUCT_MANAGER_CAPABILITY_IDS,
            upstream=ceo_artifact,
        )
        return self._execute(
            execution_id,
            twin,
            assignment,
            authority,
            intake,
            LeadershipArtifactKind.PRODUCT_MANAGER_PLAN,
            upstream=ceo_artifact,
        )

    def get(self, tenant_id: str, execution_id: str) -> LeadershipArtifact:
        return self._store.load(tenant_id, execution_id)

    def _execute(
        self,
        execution_id: str,
        twin: DigitalTwinDefinition,
        assignment: DigitalTwinAssignment,
        authority: DelegatedAuthority,
        intake: OpportunityIntake,
        kind: LeadershipArtifactKind,
        *,
        upstream: LeadershipArtifact | None,
    ) -> LeadershipArtifact:
        receipt = self._runtime.execute(
            execution_id=execution_id,
            twin=twin,
            assignment=assignment,
            authority=authority,
        )
        if receipt.status is not DigitalTwinExecutionStatus.SUCCEEDED:
            raise LeadershipWorkforcePolicyError(
                "Leadership Digital Twin execution did not produce a successful draft"
            )
        request = _provider_request(execution_id, twin, assignment, authority)
        if request.digest != receipt.request_digest:
            raise LeadershipWorkforcePolicyError(
                "Leadership receipt does not bind the rebuilt provider request"
            )
        result = self._provider.render(request)
        if result.output_digest != receipt.output_digest:
            raise LeadershipWorkforcePolicyError(
                "Leadership output does not match the execution receipt"
            )
        artifact = _artifact_from_output(
            result.output,
            kind=kind,
            intake=intake,
            execution_id=execution_id,
            twin=twin,
            assignment=assignment,
            authority=authority,
            receipt=receipt,
            upstream=upstream,
        )
        return self._store.save(artifact)

    def _validate_profile(
        self,
        intake: OpportunityIntake,
        twin: DigitalTwinDefinition,
        authority: DelegatedAuthority,
        *,
        role: AgentRole,
        capability_ids: tuple[str, ...],
        action_ids: tuple[str, ...],
        objective: str,
    ) -> None:
        if not isinstance(intake, OpportunityIntake):
            raise LeadershipWorkforcePolicyError("Opportunity intake is invalid")
        if not isinstance(twin, DigitalTwinDefinition) or not isinstance(
            authority, DelegatedAuthority
        ):
            raise LeadershipWorkforcePolicyError("Leadership authority is invalid")
        try:
            validate_action_profile(authority.allowed_action_ids, action_ids)
        except ValueError as error:
            raise LeadershipWorkforcePolicyError(
                "Leadership authority does not match its exact role profile"
            ) from error
        if not (
            twin.business_role is authority.business_role is role
            and twin.provider_id == self._provider.provider_id
            and twin.capability_ids == capability_ids
            and twin.approved_tool_ids == ()
            and authority.tenant_id == intake.tenant_id
            and authority.allowed_tool_ids == ()
            and authority.max_tool_calls == 0
            and not authority.live_provider_allowed
            and authority.objective_digest
            == hashlib.sha256(objective.encode("utf-8")).hexdigest()
        ):
            raise LeadershipWorkforcePolicyError(
                "Leadership role, capability, objective, tool, or tenant boundary does not match"
            )

    def _assignment(
        self,
        intake: OpportunityIntake,
        twin: DigitalTwinDefinition,
        authority: DelegatedAuthority,
        objective: str,
        capability_ids: tuple[str, ...],
        *,
        upstream: LeadershipArtifact | None,
    ) -> DigitalTwinAssignment:
        context = [
            ContextValue("opportunity_id", intake.opportunity_id),
            ContextValue("opportunity_digest", intake.digest),
            ContextValue("title", intake.title),
            ContextValue("problem_statement", intake.problem_statement),
            ContextValue("pilot_status", intake.pilot_status),
        ]
        context.extend(
            ContextValue(f"target_user_{index}", value)
            for index, value in enumerate(intake.target_users, start=1)
        )
        context.extend(
            ContextValue(f"desired_outcome_{index}", value)
            for index, value in enumerate(intake.desired_outcomes, start=1)
        )
        context.extend(
            ContextValue(f"constraint_{index}", value)
            for index, value in enumerate(intake.constraints, start=1)
        )
        if upstream is not None:
            context.extend(
                (
                    ContextValue("upstream_artifact_digest", upstream.digest),
                    ContextValue("upstream_summary", upstream.summary),
                )
            )
        return DigitalTwinAssignment(
            assignment_id=authority.assignment_id,
            tenant_id=intake.tenant_id,
            twin_id=twin.twin_id,
            business_role=twin.business_role,
            objective=objective,
            context=tuple(context),
            required_capability_ids=capability_ids,
            requested_tool_ids=(),
            authority_id=authority.authority_id,
            authority_digest=authority.digest,
            created_at=self._now(),
        )

    def _validate_ceo_handoff(
        self,
        intake: OpportunityIntake,
        artifact: LeadershipArtifact,
    ) -> None:
        if not isinstance(artifact, LeadershipArtifact) or not (
            artifact.kind is LeadershipArtifactKind.CEO_OPPORTUNITY_BRIEF
            and artifact.business_role is AgentRole.CEO
            and artifact.tenant_id == intake.tenant_id
            and artifact.opportunity_id == intake.opportunity_id
            and artifact.opportunity_digest == intake.digest
            and artifact.status == ARTIFACT_STATUS
            and artifact.pilot_status == PILOT_STATUS
        ):
            raise LeadershipWorkforcePolicyError("CEO-to-Product-Manager handoff is invalid")
        persisted = self._store.load(artifact.tenant_id, artifact.execution_id)
        if persisted != artifact:
            raise LeadershipWorkforcePolicyError(
                "Product Manager requires the exact persisted CEO brief"
            )

    def _now(self) -> datetime:
        value = self._clock()
        if (
            not isinstance(value, datetime)
            or value.tzinfo is None
            or value.utcoffset() is None
        ):
            raise ValueError("Leadership workforce clock must be timezone-aware")
        return value.astimezone(timezone.utc)


def _provider_request(
    execution_id: str,
    twin: DigitalTwinDefinition,
    assignment: DigitalTwinAssignment,
    authority: DelegatedAuthority,
) -> ProviderExecutionRequest:
    return ProviderExecutionRequest(
        execution_id=execution_id,
        provider_id=twin.provider_id,
        twin_id=twin.twin_id,
        twin_digest=twin.digest,
        assignment_id=assignment.assignment_id,
        assignment_digest=assignment.digest,
        authority_id=authority.authority_id,
        authority_digest=authority.digest,
        tenant_id=assignment.tenant_id,
        business_role=assignment.business_role,
        objective=assignment.objective,
        context=assignment.context,
        required_capability_ids=assignment.required_capability_ids,
        allowed_action_ids=authority.allowed_action_ids,
        allowed_tool_ids=assignment.requested_tool_ids,
        authority_expires_at=authority.expires_at,
        max_tool_calls=authority.max_tool_calls,
        max_output_bytes=authority.max_output_bytes,
    )


def _artifact_from_output(
    output: tuple[ContextValue, ...],
    *,
    kind: LeadershipArtifactKind,
    intake: OpportunityIntake,
    execution_id: str,
    twin: DigitalTwinDefinition,
    assignment: DigitalTwinAssignment,
    authority: DelegatedAuthority,
    receipt,
    upstream: LeadershipArtifact | None,
) -> LeadershipArtifact:
    values = {item.key: item.value for item in output}
    expected = {
        "artifact_kind",
        "summary",
        "goals_json",
        "clarification_questions_json",
        "status_state",
        "completed_items_json",
        "next_actions_json",
        "blockers_json",
        "human_decisions_json",
        "artifact_status",
        "pilot_status",
    }
    if kind is LeadershipArtifactKind.PRODUCT_MANAGER_PLAN:
        expected.update({"scope_in_json", "scope_out_json", "plan_items_json"})
    if len(values) != len(output) or set(values) != expected:
        raise LeadershipWorkforcePolicyError("Leadership provider output is not closed")
    if (
        values["artifact_kind"] != kind.value
        or values["artifact_status"] != ARTIFACT_STATUS
        or values["pilot_status"] != PILOT_STATUS
        or values["status_state"] != WORK_STATUS
    ):
        raise LeadershipWorkforcePolicyError("Leadership provider output state is invalid")
    try:
        status = LeadershipStatusReport(
            state=values["status_state"],
            completed_items=_json_items(values["completed_items_json"]),
            next_actions=_json_items(values["next_actions_json"]),
            blockers=_json_items(values["blockers_json"]),
            human_decisions_required=_json_items(values["human_decisions_json"]),
        )
        return LeadershipArtifact(
            artifact_id=artifact_id_for(kind, execution_id),
            kind=kind,
            tenant_id=intake.tenant_id,
            opportunity_id=intake.opportunity_id,
            execution_id=execution_id,
            assignment_id=assignment.assignment_id,
            twin_id=twin.twin_id,
            business_role=twin.business_role,
            provider_id=twin.provider_id,
            opportunity_digest=intake.digest,
            upstream_artifact_digest=None if upstream is None else upstream.digest,
            summary=values["summary"],
            goals=_json_items(values["goals_json"]),
            scope_in=_json_items(values["scope_in_json"])
            if "scope_in_json" in values
            else (),
            scope_out=_json_items(values["scope_out_json"])
            if "scope_out_json" in values
            else (),
            clarification_questions=_json_items(
                values["clarification_questions_json"]
            ),
            plan_items=_json_items(values["plan_items_json"])
            if "plan_items_json" in values
            else (),
            status_report=status,
            authority_digest=authority.digest,
            assignment_digest=assignment.digest,
            request_digest=receipt.request_digest,
            output_digest=receipt.output_digest,
            receipt_digest=receipt.digest,
            generated_at=receipt.completed_at,
        )
    except (TypeError, ValueError, json.JSONDecodeError) as error:
        raise LeadershipWorkforcePolicyError(
            "Leadership provider output failed typed validation"
        ) from error


def _json_items(value: str) -> tuple[str, ...]:
    decoded = json.loads(value)
    if not isinstance(decoded, list) or any(not isinstance(item, str) for item in decoded):
        raise ValueError("Leadership output collection is invalid")
    return tuple(decoded)
