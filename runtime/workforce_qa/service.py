"""Governed source-bound composition for the ASCOS Day 26 QA Engineer."""

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
from runtime.workforce_engineering import (
    ENGINEERING_ROLES,
    EngineeringWorkArtifact,
    FileEngineeringArtifactStore,
)
from runtime.workforce_qa.errors import QAWorkforcePolicyError
from runtime.workforce_qa.models import (
    ARCHITECTURE_STATUS,
    ARTIFACT_STATUS,
    ASSIGNMENT_STATUS,
    DEFECT_STATUS,
    ENGINEERING_STATUS,
    PILOT_STATUS,
    QA_ACTIONS,
    QA_CAPABILITIES,
    QA_ROLE,
    WORK_STATUS,
    QAAutomatedTestSpec,
    QAAutomationKind,
    QADefectKind,
    QADefectReport,
    QADefectSeverity,
    QAEngineeringSource,
    QAIntegrationTestSpec,
    QAStatusReport,
    QATestLevel,
    QATestPlanItem,
    QAWorkArtifact,
    QAWorkOrder,
    artifact_id_for,
)
from runtime.workforce_qa.persistence import FileQAArtifactStore
from runtime.workforce_qa.provider import QAEngineerProvider


def qa_objective(
    work_order: QAWorkOrder,
    architecture: ArchitectureProposalArtifact,
    engineering_artifacts: tuple[EngineeringWorkArtifact, ...],
) -> str:
    """Return the exact bounded objective for one QA planning assignment."""

    if not isinstance(work_order, QAWorkOrder) or not isinstance(
        architecture, ArchitectureProposalArtifact
    ):
        raise TypeError("QA objective source is invalid")
    if not isinstance(engineering_artifacts, tuple) or any(
        not isinstance(item, EngineeringWorkArtifact) for item in engineering_artifacts
    ):
        raise TypeError("QA Engineering sources are invalid")
    source_digest = hashlib.sha256(
        "|".join(item.digest for item in engineering_artifacts).encode("utf-8")
    ).hexdigest()
    return (
        f"Execute bounded QA_ENGINEER work order {work_order.work_order_id} "
        f"({work_order.digest}) against architecture {architecture.artifact_id} "
        f"({architecture.digest}) and the exact ordered Engineering source set "
        f"({source_digest}); produce typed QA plans and draft defects only, and do not write or "
        "run tests, access a workspace or repository, perform Security, DevOps, Documentation, "
        "or orchestration work, approve quality, merge, deploy, release, or select a pilot."
    )


class QAWorkforceService:
    """Execute the QA profile through one shared fail-closed runtime boundary."""

    def __init__(
        self,
        runtime: DigitalTwinRuntime,
        provider: QAEngineerProvider,
        architecture_store: FileArchitectureArtifactStore,
        engineering_store: FileEngineeringArtifactStore,
        store: FileQAArtifactStore,
        *,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        if not isinstance(runtime, DigitalTwinRuntime):
            raise TypeError("QA runtime must be a DigitalTwinRuntime")
        if not isinstance(provider, QAEngineerProvider):
            raise TypeError("QA provider is invalid")
        if not isinstance(architecture_store, FileArchitectureArtifactStore):
            raise TypeError("QA architecture store is invalid")
        if not isinstance(engineering_store, FileEngineeringArtifactStore):
            raise TypeError("QA Engineering store is invalid")
        if not isinstance(store, FileQAArtifactStore):
            raise TypeError("QA artifact store is invalid")
        self._runtime = runtime
        self._provider = provider
        self._architecture_store = architecture_store
        self._engineering_store = engineering_store
        self._store = store
        self._clock = clock or (lambda: datetime.now(timezone.utc))

    def run(
        self,
        *,
        execution_id: str,
        twin: DigitalTwinDefinition,
        authority: DelegatedAuthority,
        work_order: QAWorkOrder,
        architecture: ArchitectureProposalArtifact,
        engineering_artifacts: tuple[EngineeringWorkArtifact, ...],
    ) -> QAWorkArtifact:
        """Create or reopen one exact source-bound QA artifact."""

        self._validate_sources(work_order, architecture, engineering_artifacts)
        objective = qa_objective(work_order, architecture, engineering_artifacts)
        self._validate_profile(twin, authority, work_order, objective)
        assignment = self._assignment(
            work_order,
            architecture,
            engineering_artifacts,
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
            raise QAWorkforcePolicyError(
                "QA execution did not produce a successful bounded output"
            )
        request = _provider_request(execution_id, twin, assignment, authority)
        if request.digest != receipt.request_digest:
            raise QAWorkforcePolicyError(
                "QA receipt does not bind the rebuilt provider request"
            )
        result = self._provider.render(request)
        if result.output_digest != receipt.output_digest:
            raise QAWorkforcePolicyError("QA output does not match the execution receipt")
        artifact = _artifact_from_output(
            result.output,
            work_order=work_order,
            architecture=architecture,
            engineering_artifacts=engineering_artifacts,
            execution_id=execution_id,
            twin=twin,
            assignment=assignment,
            authority=authority,
            receipt=receipt,
        )
        return self._store.save(artifact)

    def get(self, tenant_id: str, execution_id: str) -> QAWorkArtifact:
        return self._store.load(tenant_id, execution_id)

    def _validate_sources(
        self,
        work_order: QAWorkOrder,
        architecture: ArchitectureProposalArtifact,
        engineering_artifacts: tuple[EngineeringWorkArtifact, ...],
    ) -> None:
        if not isinstance(work_order, QAWorkOrder) or not isinstance(
            architecture, ArchitectureProposalArtifact
        ):
            raise QAWorkforcePolicyError("QA source is invalid")
        if (
            not isinstance(engineering_artifacts, tuple)
            or len(engineering_artifacts) != 4
            or any(
                not isinstance(item, EngineeringWorkArtifact)
                for item in engineering_artifacts
            )
        ):
            raise QAWorkforcePolicyError("QA requires four exact Engineering sources")
        if not (
            architecture.business_role is AgentRole.SOFTWARE_ARCHITECT
            and architecture.tenant_id == work_order.tenant_id
            and architecture.opportunity_id == work_order.opportunity_id
            and architecture.digest == work_order.architecture_artifact_digest
            and architecture.status == ARCHITECTURE_STATUS
            and architecture.pilot_status == PILOT_STATUS
            and work_order.business_role is QA_ROLE
            and work_order.status == ASSIGNMENT_STATUS
            and work_order.pilot_status == PILOT_STATUS
            and tuple(item.business_role for item in engineering_artifacts)
            == ENGINEERING_ROLES
            and tuple(item.digest for item in engineering_artifacts)
            == work_order.engineering_artifact_digests
            and all(item.tenant_id == work_order.tenant_id for item in engineering_artifacts)
            and all(
                item.opportunity_id == work_order.opportunity_id
                for item in engineering_artifacts
            )
            and all(
                item.opportunity_digest == architecture.opportunity_digest
                for item in engineering_artifacts
            )
            and all(
                item.architecture_artifact_id == architecture.artifact_id
                and item.architecture_artifact_digest == architecture.digest
                and item.architecture_status == ARCHITECTURE_STATUS
                for item in engineering_artifacts
            )
            and all(item.status == ENGINEERING_STATUS for item in engineering_artifacts)
            and all(item.pilot_status == PILOT_STATUS for item in engineering_artifacts)
        ):
            raise QAWorkforcePolicyError(
                "QA assignment requires the exact bounded architecture and Engineering sources"
            )
        persisted_architecture = self._architecture_store.load(
            architecture.tenant_id, architecture.execution_id
        )
        if persisted_architecture != architecture:
            raise QAWorkforcePolicyError(
                "QA architecture source does not match persisted state"
            )
        for source in engineering_artifacts:
            if self._engineering_store.load(source.tenant_id, source.execution_id) != source:
                raise QAWorkforcePolicyError(
                    "QA Engineering source does not match persisted state"
                )

    def _validate_profile(
        self,
        twin: DigitalTwinDefinition,
        authority: DelegatedAuthority,
        work_order: QAWorkOrder,
        objective: str,
    ) -> None:
        if not isinstance(twin, DigitalTwinDefinition) or not isinstance(
            authority, DelegatedAuthority
        ):
            raise QAWorkforcePolicyError("QA authority is invalid")
        if not (
            twin.business_role is authority.business_role is work_order.business_role is QA_ROLE
            and twin.provider_id == self._provider.provider_id
            and twin.capability_ids == QA_CAPABILITIES
            and twin.approved_tool_ids == ()
            and authority.tenant_id == work_order.tenant_id
            and authority.assignment_id == work_order.assignment_id
            and authority.twin_id == twin.twin_id
            and authority.allowed_action_ids == QA_ACTIONS
            and authority.allowed_tool_ids == ()
            and authority.max_tool_calls == 0
            and not authority.live_provider_allowed
            and authority.issued_at <= work_order.issued_at <= authority.expires_at
            and authority.objective_digest
            == hashlib.sha256(objective.encode("utf-8")).hexdigest()
        ):
            raise QAWorkforcePolicyError(
                "QA role, capability, authority, assignment, tool, or tenant boundary does not match"
            )

    def _assignment(
        self,
        work_order: QAWorkOrder,
        architecture: ArchitectureProposalArtifact,
        engineering_artifacts: tuple[EngineeringWorkArtifact, ...],
        twin: DigitalTwinDefinition,
        authority: DelegatedAuthority,
        objective: str,
    ) -> DigitalTwinAssignment:
        sources = tuple(
            {
                "artifact_digest": item.digest,
                "business_role": item.business_role.value,
                "interface_contract_ids": tuple(
                    contract.contract_id for contract in item.interface_contracts
                ),
                "target_component_ids": item.target_component_ids,
                "status": item.status,
                "pilot_status": item.pilot_status,
            }
            for item in engineering_artifacts
        )
        context = (
            ContextValue("work_order_id", work_order.work_order_id),
            ContextValue("work_order_digest", work_order.digest),
            ContextValue("work_order_status", work_order.status),
            ContextValue("assignment_title", work_order.title),
            ContextValue("assignment_objective", work_order.objective),
            ContextValue("qa_role", work_order.business_role.value),
            ContextValue("opportunity_id", work_order.opportunity_id),
            ContextValue("opportunity_digest", architecture.opportunity_digest),
            ContextValue("opportunity_title", architecture.title),
            ContextValue("architecture_artifact_id", architecture.artifact_id),
            ContextValue("architecture_artifact_digest", architecture.digest),
            ContextValue("architecture_status", architecture.status),
            ContextValue(
                "engineering_artifact_digests_json",
                _json(work_order.engineering_artifact_digests),
            ),
            ContextValue("engineering_sources_json", _json(sources)),
            ContextValue("acceptance_checks_json", _json(work_order.acceptance_checks)),
            ContextValue("quality_risks_json", _json(work_order.quality_risks)),
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
            required_capability_ids=QA_CAPABILITIES,
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
            raise ValueError("QA workforce clock must be timezone-aware")
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
    work_order: QAWorkOrder,
    architecture: ArchitectureProposalArtifact,
    engineering_artifacts: tuple[EngineeringWorkArtifact, ...],
    execution_id: str,
    twin: DigitalTwinDefinition,
    assignment: DigitalTwinAssignment,
    authority: DelegatedAuthority,
    receipt: DigitalTwinExecutionReceipt,
) -> QAWorkArtifact:
    values = {item.key: item.value for item in output}
    expected = {
        "title",
        "summary",
        "test_plan_backend_json",
        "test_plan_frontend_json",
        "test_plan_ai_json",
        "test_plan_data_json",
        "automated_test_backend_json",
        "automated_test_frontend_json",
        "automated_test_ai_json",
        "automated_test_data_json",
        "integration_test_interface_service_json",
        "integration_test_service_data_json",
        "defect_reports_json",
        "coverage_requirements_json",
        "handoff_notes_json",
        "status_state",
        "completed_items_json",
        "next_actions_json",
        "blockers_json",
        "escalations_json",
        "artifact_status",
        "architecture_status",
        "engineering_status",
        "defect_status",
        "pilot_status",
        "acceptance_checks_json",
    }
    if len(values) != len(output) or set(values) != expected:
        raise QAWorkforcePolicyError("QA provider output is not closed")
    if not (
        values["artifact_status"] == ARTIFACT_STATUS
        and values["architecture_status"] == ARCHITECTURE_STATUS
        and values["engineering_status"] == ENGINEERING_STATUS
        and values["defect_status"] == DEFECT_STATUS
        and values["pilot_status"] == PILOT_STATUS
        and values["status_state"] == WORK_STATUS
    ):
        raise QAWorkforcePolicyError("QA provider output state is invalid")
    try:
        acceptance_checks = _string_items(values["acceptance_checks_json"])
        if acceptance_checks != work_order.acceptance_checks:
            raise ValueError("QA acceptance checks changed")
        sources = tuple(
            QAEngineeringSource(
                artifact_id=item.artifact_id,
                execution_id=item.execution_id,
                business_role=item.business_role,
                artifact_digest=item.digest,
                architecture_artifact_digest=item.architecture_artifact_digest,
                target_component_ids=item.target_component_ids,
                interface_contract_ids=tuple(
                    contract.contract_id for contract in item.interface_contracts
                ),
                status=item.status,
                pilot_status=item.pilot_status,
            )
            for item in engineering_artifacts
        )
        return QAWorkArtifact(
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
            sources=sources,
            capability_ids=QA_CAPABILITIES,
            action_ids=QA_ACTIONS,
            title=values["title"],
            summary=values["summary"],
            test_plan_items=_test_plan_items(
                values["test_plan_backend_json"],
                values["test_plan_frontend_json"],
                values["test_plan_ai_json"],
                values["test_plan_data_json"],
            ),
            automated_test_specs=_automated_specs(
                values["automated_test_backend_json"],
                values["automated_test_frontend_json"],
                values["automated_test_ai_json"],
                values["automated_test_data_json"],
            ),
            integration_test_specs=_integration_specs(
                values["integration_test_interface_service_json"],
                values["integration_test_service_data_json"],
            ),
            defect_reports=_defects(values["defect_reports_json"]),
            acceptance_checks=acceptance_checks,
            coverage_requirements=_string_items(values["coverage_requirements_json"]),
            handoff_notes=_string_items(values["handoff_notes_json"]),
            status_report=QAStatusReport(
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
        raise QAWorkforcePolicyError("QA provider output failed typed validation") from error


def _test_plan_items(*values: str) -> tuple[QATestPlanItem, ...]:
    keys = {
        "item_id",
        "level",
        "source_engineering_artifact_digest",
        "target_component_ids",
        "objective",
        "preconditions",
        "expected_outcome",
    }
    records = tuple(item for value in values for item in _records(value, keys))
    return tuple(
        QATestPlanItem(
            item_id=item["item_id"],
            level=QATestLevel(item["level"]),
            source_engineering_artifact_digest=item[
                "source_engineering_artifact_digest"
            ],
            target_component_ids=_record_string_items(item, "target_component_ids"),
            objective=item["objective"],
            preconditions=_record_string_items(item, "preconditions"),
            expected_outcome=item["expected_outcome"],
        )
        for item in records
    )


def _automated_specs(*values: str) -> tuple[QAAutomatedTestSpec, ...]:
    keys = {
        "spec_id",
        "kind",
        "source_engineering_artifact_digest",
        "target_component_id",
        "scenario",
        "fixture",
        "assertions",
        "negative_cases",
        "execution_state",
    }
    records = tuple(item for value in values for item in _records(value, keys))
    return tuple(
        QAAutomatedTestSpec(
            spec_id=item["spec_id"],
            kind=QAAutomationKind(item["kind"]),
            source_engineering_artifact_digest=item[
                "source_engineering_artifact_digest"
            ],
            target_component_id=item["target_component_id"],
            scenario=item["scenario"],
            fixture=item["fixture"],
            assertions=_record_string_items(item, "assertions"),
            negative_cases=_record_string_items(item, "negative_cases"),
            execution_state=item["execution_state"],
        )
        for item in records
    )


def _integration_specs(*values: str) -> tuple[QAIntegrationTestSpec, ...]:
    keys = {
        "spec_id",
        "source_engineering_artifact_digests",
        "interface_contract_ids",
        "scenario",
        "preconditions",
        "steps",
        "expected_outcome",
        "failure_behavior",
        "execution_state",
    }
    records = tuple(item for value in values for item in _records(value, keys))
    return tuple(
        QAIntegrationTestSpec(
            spec_id=item["spec_id"],
            source_engineering_artifact_digests=_record_string_items(
                item, "source_engineering_artifact_digests"
            ),
            interface_contract_ids=_record_string_items(item, "interface_contract_ids"),
            scenario=item["scenario"],
            preconditions=_record_string_items(item, "preconditions"),
            steps=_record_string_items(item, "steps"),
            expected_outcome=item["expected_outcome"],
            failure_behavior=item["failure_behavior"],
            execution_state=item["execution_state"],
        )
        for item in records
    )


def _defects(value: str) -> tuple[QADefectReport, ...]:
    records = _records(
        value,
        {
            "defect_id",
            "kind",
            "severity",
            "source_engineering_artifact_digest",
            "title",
            "evidence_basis",
            "expected_behavior",
            "observed_risk",
            "reproduction_conditions",
            "status",
        },
    )
    return tuple(
        QADefectReport(
            defect_id=item["defect_id"],
            kind=QADefectKind(item["kind"]),
            severity=QADefectSeverity(item["severity"]),
            source_engineering_artifact_digest=item[
                "source_engineering_artifact_digest"
            ],
            title=item["title"],
            evidence_basis=item["evidence_basis"],
            expected_behavior=item["expected_behavior"],
            observed_risk=item["observed_risk"],
            reproduction_conditions=_record_string_items(
                item, "reproduction_conditions"
            ),
            status=item["status"],
        )
        for item in records
    )


def _records(value: str, keys: set[str]) -> tuple[dict, ...]:
    decoded = json.loads(value)
    if (
        not isinstance(decoded, list)
        or any(not isinstance(item, dict) or set(item) != keys for item in decoded)
    ):
        raise ValueError("QA structured output is invalid")
    return tuple(decoded)


def _string_items(value: str) -> tuple[str, ...]:
    decoded = json.loads(value)
    if not isinstance(decoded, list) or any(not isinstance(item, str) for item in decoded):
        raise ValueError("QA output collection is invalid")
    return tuple(decoded)


def _record_string_items(value: dict, key: str) -> tuple[str, ...]:
    items = value[key]
    if not isinstance(items, list) or any(not isinstance(item, str) for item in items):
        raise ValueError("QA nested output collection is invalid")
    return tuple(items)


def _json(value: object) -> str:
    return json.dumps(value, separators=(",", ":"), ensure_ascii=False)
