"""Governed shared composition for the ASCOS Day 25 Engineering agent family."""

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
from runtime.workforce_architecture import (
    ArchitectureProposalArtifact,
    FileArchitectureArtifactStore,
)
from runtime.workforce_engineering.errors import EngineeringWorkforcePolicyError
from runtime.workforce_engineering.models import (
    ARCHITECTURE_STATUS,
    ARTIFACT_STATUS,
    ASSIGNMENT_STATUS,
    PILOT_STATUS,
    WORK_STATUS,
    EngineeringChangeKind,
    EngineeringContractKind,
    EngineeringDiscipline,
    EngineeringImplementationItem,
    EngineeringInterfaceContract,
    EngineeringStatusReport,
    EngineeringWorkArtifact,
    EngineeringWorkOrder,
    action_ids_for,
    artifact_id_for,
    capability_ids_for,
)
from runtime.workforce_engineering.persistence import FileEngineeringArtifactStore
from runtime.workforce_engineering.provider import EngineeringAgentProvider


def engineering_objective(
    work_order: EngineeringWorkOrder,
    architecture: ArchitectureProposalArtifact,
) -> str:
    """Return the exact bounded objective for a role-specific Engineering assignment."""

    if not isinstance(work_order, EngineeringWorkOrder) or not isinstance(
        architecture, ArchitectureProposalArtifact
    ):
        raise TypeError("Engineering objective source is invalid")
    return (
        f"Execute bounded {work_order.business_role.value} work order "
        f"{work_order.work_order_id} ({work_order.digest}) against architecture artifact "
        f"{architecture.artifact_id} ({architecture.digest}); produce typed engineering output "
        "only and do not access a workspace or repository, run commands, perform QA or security "
        "approval, merge, deploy, release, orchestrate agents, or select a pilot."
    )


class EngineeringWorkforceService:
    """Execute four role profiles through one shared, fail-closed runtime boundary."""

    def __init__(
        self,
        runtime: DigitalTwinRuntime,
        provider: EngineeringAgentProvider,
        architecture_store: FileArchitectureArtifactStore,
        store: FileEngineeringArtifactStore,
        *,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        if not isinstance(runtime, DigitalTwinRuntime):
            raise TypeError("Engineering runtime must be a DigitalTwinRuntime")
        if not isinstance(provider, EngineeringAgentProvider):
            raise TypeError("Engineering provider is invalid")
        if not isinstance(architecture_store, FileArchitectureArtifactStore):
            raise TypeError("Architecture artifact store is invalid")
        if not isinstance(store, FileEngineeringArtifactStore):
            raise TypeError("Engineering artifact store is invalid")
        self._runtime = runtime
        self._provider = provider
        self._architecture_store = architecture_store
        self._store = store
        self._clock = clock or (lambda: datetime.now(timezone.utc))

    def run(
        self,
        *,
        execution_id: str,
        twin: DigitalTwinDefinition,
        authority: DelegatedAuthority,
        work_order: EngineeringWorkOrder,
        architecture: ArchitectureProposalArtifact,
    ) -> EngineeringWorkArtifact:
        """Create or reopen one exact role-bound Engineering execution artifact."""

        self._validate_source(work_order, architecture)
        objective = engineering_objective(work_order, architecture)
        self._validate_profile(twin, authority, work_order, objective)
        assignment = self._assignment(work_order, architecture, twin, authority, objective)
        receipt = self._runtime.execute(
            execution_id=execution_id,
            twin=twin,
            assignment=assignment,
            authority=authority,
        )
        if receipt.status is not DigitalTwinExecutionStatus.SUCCEEDED:
            raise EngineeringWorkforcePolicyError(
                "Engineering execution did not produce a successful bounded output"
            )
        request = _provider_request(execution_id, twin, assignment, authority)
        if request.digest != receipt.request_digest:
            raise EngineeringWorkforcePolicyError(
                "Engineering receipt does not bind the rebuilt provider request"
            )
        result = self._provider.render(request)
        if result.output_digest != receipt.output_digest:
            raise EngineeringWorkforcePolicyError(
                "Engineering output does not match the execution receipt"
            )
        artifact = _artifact_from_output(
            result.output,
            work_order=work_order,
            architecture=architecture,
            execution_id=execution_id,
            twin=twin,
            assignment=assignment,
            authority=authority,
            receipt=receipt,
        )
        return self._store.save(artifact)

    def get(self, tenant_id: str, execution_id: str) -> EngineeringWorkArtifact:
        return self._store.load(tenant_id, execution_id)

    def _validate_source(
        self,
        work_order: EngineeringWorkOrder,
        architecture: ArchitectureProposalArtifact,
    ) -> None:
        if not isinstance(work_order, EngineeringWorkOrder) or not isinstance(
            architecture, ArchitectureProposalArtifact
        ):
            raise EngineeringWorkforcePolicyError("Engineering source is invalid")
        component_ids = {item.component_id for item in architecture.components}
        if not (
            architecture.business_role is AgentRole.SOFTWARE_ARCHITECT
            and architecture.tenant_id == work_order.tenant_id
            and architecture.opportunity_id == work_order.opportunity_id
            and architecture.digest == work_order.architecture_artifact_digest
            and architecture.status == ARCHITECTURE_STATUS
            and architecture.pilot_status == PILOT_STATUS
            and work_order.status == ASSIGNMENT_STATUS
            and work_order.pilot_status == PILOT_STATUS
            and set(work_order.target_component_ids) <= component_ids
        ):
            raise EngineeringWorkforcePolicyError(
                "Engineering assignment requires the exact bounded architecture source"
            )
        persisted = self._architecture_store.load(
            architecture.tenant_id, architecture.execution_id
        )
        if persisted != architecture:
            raise EngineeringWorkforcePolicyError(
                "Engineering architecture source does not match persisted state"
            )

    def _validate_profile(
        self,
        twin: DigitalTwinDefinition,
        authority: DelegatedAuthority,
        work_order: EngineeringWorkOrder,
        objective: str,
    ) -> None:
        if not isinstance(twin, DigitalTwinDefinition) or not isinstance(
            authority, DelegatedAuthority
        ):
            raise EngineeringWorkforcePolicyError("Engineering authority is invalid")
        role = work_order.business_role
        if not (
            twin.business_role is authority.business_role is role
            and twin.provider_id == self._provider.provider_id
            and twin.capability_ids == capability_ids_for(role)
            and twin.approved_tool_ids == ()
            and authority.tenant_id == work_order.tenant_id
            and authority.assignment_id == work_order.assignment_id
            and authority.allowed_action_ids == action_ids_for(role)
            and authority.allowed_tool_ids == ()
            and authority.max_tool_calls == 0
            and not authority.live_provider_allowed
            and authority.issued_at <= work_order.issued_at <= authority.expires_at
            and authority.objective_digest
            == hashlib.sha256(objective.encode("utf-8")).hexdigest()
        ):
            raise EngineeringWorkforcePolicyError(
                "Engineering role, capability, authority, assignment, tool, or tenant boundary does not match"
            )

    def _assignment(
        self,
        work_order: EngineeringWorkOrder,
        architecture: ArchitectureProposalArtifact,
        twin: DigitalTwinDefinition,
        authority: DelegatedAuthority,
        objective: str,
    ) -> DigitalTwinAssignment:
        selected_components = tuple(
            {
                "component_id": item.component_id,
                "name": item.name,
                "responsibility": item.responsibility,
                "data_responsibility": item.data_responsibility,
            }
            for item in architecture.components
            if item.component_id in work_order.target_component_ids
        )
        technologies = tuple(
            {
                "area": item.area,
                "technology": item.technology,
                "status": item.status,
            }
            for item in architecture.technology_recommendations
        )
        context = (
            ContextValue("work_order_id", work_order.work_order_id),
            ContextValue("work_order_digest", work_order.digest),
            ContextValue("work_order_status", work_order.status),
            ContextValue("assignment_title", work_order.title),
            ContextValue("assignment_objective", work_order.objective),
            ContextValue("engineering_role", work_order.business_role.value),
            ContextValue("opportunity_id", work_order.opportunity_id),
            ContextValue("opportunity_digest", architecture.opportunity_digest),
            ContextValue("opportunity_title", architecture.title),
            ContextValue("architecture_artifact_id", architecture.artifact_id),
            ContextValue("architecture_artifact_digest", architecture.digest),
            ContextValue("architecture_status", architecture.status),
            ContextValue("architecture_summary", architecture.summary),
            ContextValue("target_components_json", _json(selected_components)),
            ContextValue("technology_recommendations_json", _json(technologies)),
            ContextValue("acceptance_checks_json", _json(work_order.acceptance_checks)),
            ContextValue("constraints_json", _json(work_order.constraints)),
            ContextValue("pilot_status", work_order.pilot_status),
        )
        return DigitalTwinAssignment(
            assignment_id=work_order.assignment_id,
            tenant_id=work_order.tenant_id,
            twin_id=twin.twin_id,
            business_role=work_order.business_role,
            objective=objective,
            context=context,
            required_capability_ids=capability_ids_for(work_order.business_role),
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
            raise ValueError("Engineering workforce clock must be timezone-aware")
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
    work_order: EngineeringWorkOrder,
    architecture: ArchitectureProposalArtifact,
    execution_id: str,
    twin: DigitalTwinDefinition,
    assignment: DigitalTwinAssignment,
    authority: DelegatedAuthority,
    receipt: DigitalTwinExecutionReceipt,
) -> EngineeringWorkArtifact:
    values = {item.key: item.value for item in output}
    expected = {
        "title",
        "summary",
        "implementation_items_json",
        "interface_contracts_json",
        "validation_checks_json",
        "handoff_notes_json",
        "status_state",
        "completed_items_json",
        "next_actions_json",
        "blockers_json",
        "escalations_json",
        "artifact_status",
        "architecture_status",
        "pilot_status",
        "acceptance_checks_json",
    }
    if len(values) != len(output) or set(values) != expected:
        raise EngineeringWorkforcePolicyError("Engineering provider output is not closed")
    if not (
        values["artifact_status"] == ARTIFACT_STATUS
        and values["architecture_status"] == ARCHITECTURE_STATUS
        and values["pilot_status"] == PILOT_STATUS
        and values["status_state"] == WORK_STATUS
    ):
        raise EngineeringWorkforcePolicyError("Engineering provider output state is invalid")
    try:
        acceptance_checks = _string_items(values["acceptance_checks_json"])
        if acceptance_checks != work_order.acceptance_checks:
            raise ValueError("Engineering acceptance checks changed")
        return EngineeringWorkArtifact(
            artifact_id=artifact_id_for(execution_id),
            work_order_id=work_order.work_order_id,
            work_order_digest=work_order.digest,
            tenant_id=work_order.tenant_id,
            opportunity_id=work_order.opportunity_id,
            execution_id=execution_id,
            assignment_id=assignment.assignment_id,
            twin_id=twin.twin_id,
            business_role=twin.business_role,
            provider_id=twin.provider_id,
            opportunity_digest=architecture.opportunity_digest,
            architecture_artifact_id=architecture.artifact_id,
            architecture_artifact_digest=architecture.digest,
            architecture_status=values["architecture_status"],
            target_component_ids=work_order.target_component_ids,
            capability_ids=capability_ids_for(twin.business_role),
            action_ids=action_ids_for(twin.business_role),
            title=values["title"],
            summary=values["summary"],
            implementation_items=_implementation_items(values["implementation_items_json"]),
            interface_contracts=_interface_contracts(values["interface_contracts_json"]),
            acceptance_checks=acceptance_checks,
            validation_checks=_string_items(values["validation_checks_json"]),
            handoff_notes=_string_items(values["handoff_notes_json"]),
            status_report=EngineeringStatusReport(
                state=values["status_state"],
                completed_items=_string_items(values["completed_items_json"]),
                next_actions=_string_items(values["next_actions_json"]),
                blockers=_string_items(values["blockers_json"]),
                escalations=_string_items(values["escalations_json"]),
            ),
            authority_digest=authority.digest,
            assignment_digest=assignment.digest,
            request_digest=receipt.request_digest,
            output_digest=receipt.output_digest,
            receipt_digest=receipt.digest,
            generated_at=receipt.completed_at,
        )
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
        raise EngineeringWorkforcePolicyError(
            "Engineering provider output failed typed validation"
        ) from error


def _implementation_items(value: str) -> tuple[EngineeringImplementationItem, ...]:
    records = _records(
        value,
        {
            "item_id",
            "discipline",
            "target_component_id",
            "change_kind",
            "implementation",
            "expected_outcome",
        },
    )
    return tuple(
        EngineeringImplementationItem(
            item_id=item["item_id"],
            discipline=EngineeringDiscipline(item["discipline"]),
            target_component_id=item["target_component_id"],
            change_kind=EngineeringChangeKind(item["change_kind"]),
            implementation=item["implementation"],
            expected_outcome=item["expected_outcome"],
        )
        for item in records
    )


def _interface_contracts(value: str) -> tuple[EngineeringInterfaceContract, ...]:
    records = _records(
        value,
        {
            "contract_id",
            "kind",
            "name",
            "producer",
            "consumer",
            "inputs",
            "outputs",
            "failure_behavior",
        },
    )
    return tuple(
        EngineeringInterfaceContract(
            contract_id=item["contract_id"],
            kind=EngineeringContractKind(item["kind"]),
            name=item["name"],
            producer=item["producer"],
            consumer=item["consumer"],
            inputs=_record_string_items(item, "inputs"),
            outputs=_record_string_items(item, "outputs"),
            failure_behavior=item["failure_behavior"],
        )
        for item in records
    )


def _records(value: str, keys: set[str]) -> tuple[dict, ...]:
    decoded = json.loads(value)
    if (
        not isinstance(decoded, list)
        or any(not isinstance(item, dict) or set(item) != keys for item in decoded)
    ):
        raise ValueError("Engineering structured output is invalid")
    return tuple(decoded)


def _string_items(value: str) -> tuple[str, ...]:
    decoded = json.loads(value)
    if not isinstance(decoded, list) or any(not isinstance(item, str) for item in decoded):
        raise ValueError("Engineering output collection is invalid")
    return tuple(decoded)


def _record_string_items(value: dict, key: str) -> tuple[str, ...]:
    items = value[key]
    if not isinstance(items, list) or any(not isinstance(item, str) for item in items):
        raise ValueError("Engineering nested output collection is invalid")
    return tuple(items)


def _json(value: object) -> str:
    return json.dumps(value, separators=(",", ":"), ensure_ascii=False)
