"""Governed Software Architect composition on the Digital Twin runtime."""

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
    DigitalTwinExecutionReceipt,
    DigitalTwinExecutionStatus,
    DigitalTwinRuntime,
    ProviderExecutionRequest,
)
from runtime.workforce_architecture.errors import ArchitectureWorkforcePolicyError
from runtime.workforce_architecture.models import (
    ADR_STATUS,
    ARCHITECT_ACTION_IDS,
    ARCHITECT_CAPABILITY_IDS,
    ARTIFACT_STATUS,
    PILOT_STATUS,
    RECOMMENDATION_STATUS,
    WORK_STATUS,
    ArchitectureComponent,
    ArchitectureDecisionDraft,
    ArchitectureProposalArtifact,
    ArchitectureStatusReport,
    RiskLikelihood,
    RiskSeverity,
    TechnicalRisk,
    TechnologyRecommendation,
    artifact_id_for,
)
from runtime.workforce_architecture.persistence import FileArchitectureArtifactStore
from runtime.workforce_architecture.provider import SoftwareArchitectProvider
from runtime.workforce_leadership import (
    FileLeadershipArtifactStore,
    LeadershipArtifact,
    LeadershipArtifactKind,
    OpportunityIntake,
)


def architecture_objective(
    intake: OpportunityIntake,
    product_manager_artifact: LeadershipArtifact,
) -> str:
    """Return the exact proposed-only Software Architect objective."""

    if not isinstance(intake, OpportunityIntake) or not isinstance(
        product_manager_artifact, LeadershipArtifact
    ):
        raise TypeError("Software Architect source is invalid")
    return (
        f"Prepare a draft software architecture, technology recommendations, proposed ADRs, "
        f"and technical risks for {intake.opportunity_id} from Product Manager artifact "
        f"{product_manager_artifact.artifact_id}; require human review and do not create "
        "engineering tasks, write a repository, approve architecture, or select a pilot."
    )


class ArchitectureWorkforceService:
    """Execute one exact Software Architect assignment and persist its validated draft."""

    def __init__(
        self,
        runtime: DigitalTwinRuntime,
        provider: SoftwareArchitectProvider,
        leadership_store: FileLeadershipArtifactStore,
        store: FileArchitectureArtifactStore,
        *,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        if not isinstance(runtime, DigitalTwinRuntime):
            raise TypeError("Architecture runtime must be a DigitalTwinRuntime")
        if not isinstance(provider, SoftwareArchitectProvider):
            raise TypeError("Software Architect provider is invalid")
        if not isinstance(leadership_store, FileLeadershipArtifactStore):
            raise TypeError("Leadership artifact store is invalid")
        if not isinstance(store, FileArchitectureArtifactStore):
            raise TypeError("Architecture artifact store is invalid")
        self._runtime = runtime
        self._provider = provider
        self._leadership_store = leadership_store
        self._store = store
        self._clock = clock or (lambda: datetime.now(timezone.utc))

    def run(
        self,
        *,
        execution_id: str,
        twin: DigitalTwinDefinition,
        authority: DelegatedAuthority,
        intake: OpportunityIntake,
        product_manager_artifact: LeadershipArtifact,
    ) -> ArchitectureProposalArtifact:
        """Create or reopen one exact draft Software Architect proposal."""

        self._validate_source(intake, product_manager_artifact)
        objective = architecture_objective(intake, product_manager_artifact)
        self._validate_profile(intake, twin, authority, objective)
        assignment = self._assignment(
            intake,
            product_manager_artifact,
            twin,
            authority,
            objective,
        )
        receipt = self._runtime.execute(
            execution_id=execution_id,
            twin=twin,
            assignment=assignment,
            authority=authority,
        )
        if receipt.status is not DigitalTwinExecutionStatus.SUCCEEDED:
            raise ArchitectureWorkforcePolicyError(
                "Software Architect execution did not produce a successful draft"
            )
        request = _provider_request(execution_id, twin, assignment, authority)
        if request.digest != receipt.request_digest:
            raise ArchitectureWorkforcePolicyError(
                "Architecture receipt does not bind the rebuilt provider request"
            )
        result = self._provider.render(request)
        if result.output_digest != receipt.output_digest:
            raise ArchitectureWorkforcePolicyError(
                "Architecture output does not match the execution receipt"
            )
        artifact = _artifact_from_output(
            result.output,
            intake=intake,
            product_manager_artifact=product_manager_artifact,
            execution_id=execution_id,
            twin=twin,
            assignment=assignment,
            authority=authority,
            receipt=receipt,
        )
        return self._store.save(artifact)

    def get(self, tenant_id: str, execution_id: str) -> ArchitectureProposalArtifact:
        return self._store.load(tenant_id, execution_id)

    def _validate_source(
        self,
        intake: OpportunityIntake,
        artifact: LeadershipArtifact,
    ) -> None:
        if not isinstance(intake, OpportunityIntake) or not isinstance(
            artifact, LeadershipArtifact
        ):
            raise ArchitectureWorkforcePolicyError("Architecture source is invalid")
        if not (
            artifact.kind is LeadershipArtifactKind.PRODUCT_MANAGER_PLAN
            and artifact.business_role is AgentRole.PROJECT_MANAGER
            and artifact.tenant_id == intake.tenant_id
            and artifact.opportunity_id == intake.opportunity_id
            and artifact.opportunity_digest == intake.digest
            and artifact.pilot_status == PILOT_STATUS
        ):
            raise ArchitectureWorkforcePolicyError(
                "Software Architect requires the exact Product Manager plan"
            )
        persisted = self._leadership_store.load(artifact.tenant_id, artifact.execution_id)
        if persisted != artifact:
            raise ArchitectureWorkforcePolicyError(
                "Software Architect source does not match persisted Product Manager state"
            )

    def _validate_profile(
        self,
        intake: OpportunityIntake,
        twin: DigitalTwinDefinition,
        authority: DelegatedAuthority,
        objective: str,
    ) -> None:
        if not isinstance(twin, DigitalTwinDefinition) or not isinstance(
            authority, DelegatedAuthority
        ):
            raise ArchitectureWorkforcePolicyError("Architecture authority is invalid")
        if not (
            twin.business_role is authority.business_role is AgentRole.SOFTWARE_ARCHITECT
            and twin.provider_id == self._provider.provider_id
            and twin.capability_ids == ARCHITECT_CAPABILITY_IDS
            and twin.approved_tool_ids == ()
            and authority.tenant_id == intake.tenant_id
            and authority.allowed_action_ids == ARCHITECT_ACTION_IDS
            and authority.allowed_tool_ids == ()
            and authority.max_tool_calls == 0
            and not authority.live_provider_allowed
            and authority.objective_digest
            == hashlib.sha256(objective.encode("utf-8")).hexdigest()
        ):
            raise ArchitectureWorkforcePolicyError(
                "Architecture role, capability, objective, tool, or tenant boundary does not match"
            )

    def _assignment(
        self,
        intake: OpportunityIntake,
        source: LeadershipArtifact,
        twin: DigitalTwinDefinition,
        authority: DelegatedAuthority,
        objective: str,
    ) -> DigitalTwinAssignment:
        context = (
            ContextValue("opportunity_id", intake.opportunity_id),
            ContextValue("opportunity_digest", intake.digest),
            ContextValue("opportunity_title", intake.title),
            ContextValue("product_manager_artifact_id", source.artifact_id),
            ContextValue("product_manager_artifact_digest", source.digest),
            ContextValue("product_manager_summary", source.summary),
            ContextValue("goals_json", _json(source.goals)),
            ContextValue("scope_in_json", _json(source.scope_in)),
            ContextValue("scope_out_json", _json(source.scope_out)),
            ContextValue("plan_items_json", _json(source.plan_items)),
            ContextValue("pilot_status", source.pilot_status),
        )
        return DigitalTwinAssignment(
            assignment_id=authority.assignment_id,
            tenant_id=intake.tenant_id,
            twin_id=twin.twin_id,
            business_role=twin.business_role,
            objective=objective,
            context=context,
            required_capability_ids=ARCHITECT_CAPABILITY_IDS,
            requested_tool_ids=(),
            authority_id=authority.authority_id,
            authority_digest=authority.digest,
            created_at=self._now(),
        )

    def _now(self) -> datetime:
        value = self._clock()
        if (
            not isinstance(value, datetime)
            or value.tzinfo is None
            or value.utcoffset() is None
        ):
            raise ValueError("Architecture workforce clock must be timezone-aware")
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
    intake: OpportunityIntake,
    product_manager_artifact: LeadershipArtifact,
    execution_id: str,
    twin: DigitalTwinDefinition,
    assignment: DigitalTwinAssignment,
    authority: DelegatedAuthority,
    receipt: DigitalTwinExecutionReceipt,
) -> ArchitectureProposalArtifact:
    values = {item.key: item.value for item in output}
    expected = {
        "title",
        "summary",
        "domain_boundary",
        "principles_json",
        "components_json",
        "integration_points_json",
        "data_lifecycle_json",
        "security_controls_json",
        "quality_strategy_json",
        "technology_recommendations_json",
        "adr_drafts_json",
        "technical_risks_json",
        "status_state",
        "completed_items_json",
        "next_actions_json",
        "blockers_json",
        "human_decisions_json",
        "artifact_status",
        "pilot_status",
    }
    if len(values) != len(output) or set(values) != expected:
        raise ArchitectureWorkforcePolicyError("Architecture provider output is not closed")
    if (
        values["artifact_status"] != ARTIFACT_STATUS
        or values["pilot_status"] != PILOT_STATUS
        or values["status_state"] != WORK_STATUS
    ):
        raise ArchitectureWorkforcePolicyError("Architecture provider output state is invalid")
    try:
        components = _components(values["components_json"])
        technologies = _technologies(values["technology_recommendations_json"])
        adrs = _adrs(values["adr_drafts_json"])
        risks = _risks(values["technical_risks_json"])
        status = ArchitectureStatusReport(
            state=values["status_state"],
            completed_items=_string_items(values["completed_items_json"]),
            next_actions=_string_items(values["next_actions_json"]),
            blockers=_string_items(values["blockers_json"]),
            human_decisions_required=_string_items(values["human_decisions_json"]),
        )
        return ArchitectureProposalArtifact(
            artifact_id=artifact_id_for(execution_id),
            tenant_id=intake.tenant_id,
            opportunity_id=intake.opportunity_id,
            execution_id=execution_id,
            assignment_id=assignment.assignment_id,
            twin_id=twin.twin_id,
            business_role=twin.business_role,
            provider_id=twin.provider_id,
            opportunity_digest=intake.digest,
            product_manager_artifact_digest=product_manager_artifact.digest,
            title=values["title"],
            summary=values["summary"],
            domain_boundary=values["domain_boundary"],
            principles=_string_items(values["principles_json"]),
            components=components,
            integration_points=_string_items(values["integration_points_json"]),
            data_lifecycle=_string_items(values["data_lifecycle_json"]),
            security_controls=_string_items(values["security_controls_json"]),
            quality_strategy=_string_items(values["quality_strategy_json"]),
            technology_recommendations=technologies,
            adr_drafts=adrs,
            technical_risks=risks,
            status_report=status,
            authority_digest=authority.digest,
            assignment_digest=assignment.digest,
            request_digest=receipt.request_digest,
            output_digest=receipt.output_digest,
            receipt_digest=receipt.digest,
            generated_at=receipt.completed_at,
        )
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
        raise ArchitectureWorkforcePolicyError(
            "Architecture provider output failed typed validation"
        ) from error


def _components(value: str) -> tuple[ArchitectureComponent, ...]:
    records = _records(
        value,
        {"component_id", "name", "responsibility", "interfaces", "data_responsibility"},
    )
    return tuple(
        ArchitectureComponent(
            component_id=item["component_id"],
            name=item["name"],
            responsibility=item["responsibility"],
            interfaces=tuple(item["interfaces"]),
            data_responsibility=item["data_responsibility"],
        )
        for item in records
    )


def _technologies(value: str) -> tuple[TechnologyRecommendation, ...]:
    records = _records(
        value,
        {"recommendation_id", "area", "technology", "rationale", "alternatives_considered", "status"},
    )
    return tuple(
        TechnologyRecommendation(
            recommendation_id=item["recommendation_id"],
            area=item["area"],
            technology=item["technology"],
            rationale=item["rationale"],
            alternatives_considered=tuple(item["alternatives_considered"]),
            status=item["status"],
        )
        for item in records
    )


def _adrs(value: str) -> tuple[ArchitectureDecisionDraft, ...]:
    records = _records(
        value,
        {"adr_id", "title", "context", "decision", "consequences", "status", "human_approval_required"},
    )
    return tuple(
        ArchitectureDecisionDraft(
            adr_id=item["adr_id"],
            title=item["title"],
            context=item["context"],
            decision=item["decision"],
            consequences=tuple(item["consequences"]),
            status=item["status"],
            human_approval_required=item["human_approval_required"],
        )
        for item in records
    )


def _risks(value: str) -> tuple[TechnicalRisk, ...]:
    records = _records(
        value,
        {"risk_id", "title", "severity", "likelihood", "impact", "mitigation", "escalation"},
    )
    return tuple(
        TechnicalRisk(
            risk_id=item["risk_id"],
            title=item["title"],
            severity=RiskSeverity(item["severity"]),
            likelihood=RiskLikelihood(item["likelihood"]),
            impact=item["impact"],
            mitigation=item["mitigation"],
            escalation=item["escalation"],
        )
        for item in records
    )


def _records(value: str, keys: set[str]) -> tuple[dict, ...]:
    decoded = json.loads(value)
    if (
        not isinstance(decoded, list)
        or any(not isinstance(item, dict) or set(item) != keys for item in decoded)
    ):
        raise ValueError("Architecture structured output is invalid")
    return tuple(decoded)


def _string_items(value: str) -> tuple[str, ...]:
    decoded = json.loads(value)
    if not isinstance(decoded, list) or any(not isinstance(item, str) for item in decoded):
        raise ValueError("Architecture output collection is invalid")
    return tuple(decoded)


def _json(value: object) -> str:
    return json.dumps(value, separators=(",", ":"), ensure_ascii=False)
