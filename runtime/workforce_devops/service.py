"""Governed source-bound composition for the ASCOS Day 28 DevOps Engineer."""

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
from runtime.workforce_architecture import ArchitectureProposalArtifact, FileArchitectureArtifactStore
from runtime.workforce_engineering import (
    ENGINEERING_ROLES,
    EngineeringWorkArtifact,
    FileEngineeringArtifactStore,
)
from runtime.workforce_qa import FileQAArtifactStore, QAWorkArtifact
from runtime.workforce_security import FileSecurityArtifactStore, SecurityWorkArtifact
from runtime.workforce_devops.errors import DevOpsWorkforcePolicyError
from runtime.workforce_devops.models import (
    ARCHITECTURE_STATUS,
    ARTIFACT_STATUS,
    ASSIGNMENT_STATUS,
    DEVOPS_ACTIONS,
    DEVOPS_CAPABILITIES,
    DEVOPS_ROLE,
    ENGINEERING_STATUS,
    EXECUTION_STATE,
    PILOT_STATUS,
    PREVIEW_ENVIRONMENT_CLASS,
    QA_STATUS,
    SECURITY_STATUS,
    WORK_STATUS,
    CIPipelinePlan,
    DeploymentPlan,
    DevOpsEngineeringSource,
    DevOpsStatusReport,
    DevOpsWorkArtifact,
    DevOpsWorkOrder,
    MigrationPlan,
    MonitoringPlan,
    PreviewEnvironmentPlan,
    RollbackPlan,
    artifact_id_for,
)
from runtime.workforce_devops.persistence import FileDevOpsArtifactStore
from runtime.workforce_devops.provider import DevOpsEngineerProvider


def devops_objective(
    work_order: DevOpsWorkOrder,
    architecture: ArchitectureProposalArtifact,
    engineering_artifacts: tuple[EngineeringWorkArtifact, ...],
    qa_artifact: QAWorkArtifact,
    security_artifact: SecurityWorkArtifact,
) -> str:
    """Return the exact bounded objective for one DevOps preparation assignment."""

    if not isinstance(work_order, DevOpsWorkOrder) or not isinstance(architecture, ArchitectureProposalArtifact):
        raise TypeError("DevOps objective source is invalid")
    if (
        not isinstance(engineering_artifacts, tuple)
        or any(not isinstance(item, EngineeringWorkArtifact) for item in engineering_artifacts)
        or not isinstance(qa_artifact, QAWorkArtifact)
        or not isinstance(security_artifact, SecurityWorkArtifact)
    ):
        raise TypeError("DevOps workforce sources are invalid")
    source_digest = hashlib.sha256(
        "|".join(item.digest for item in engineering_artifacts).encode("utf-8")
    ).hexdigest()
    return (
        f"Execute bounded DEVOPS_ENGINEER work order {work_order.work_order_id} "
        f"({work_order.digest}) against architecture {architecture.artifact_id} "
        f"({architecture.digest}), ordered Engineering source set ({source_digest}), QA "
        f"artifact {qa_artifact.artifact_id} ({qa_artifact.digest}), and Security artifact "
        f"{security_artifact.artifact_id} ({security_artifact.digest}); produce typed CI, "
        "isolated preview, migration, deployment, monitoring, and rollback preparation only. "
        "Do not access a workspace, filesystem, repository, command, network, infrastructure, "
        "credential, or live provider; execute CI, provisioning, migration, deployment, "
        "monitoring, rollback, promotion, release, QA, Security, Documentation, or orchestration "
        "work; merge, accept risk, approve architecture or quality, or select a pilot."
    )


class DevOpsWorkforceService:
    """Execute the DevOps profile through one fail-closed runtime boundary."""

    def __init__(
        self,
        runtime: DigitalTwinRuntime,
        provider: DevOpsEngineerProvider,
        architecture_store: FileArchitectureArtifactStore,
        engineering_store: FileEngineeringArtifactStore,
        qa_store: FileQAArtifactStore,
        security_store: FileSecurityArtifactStore,
        store: FileDevOpsArtifactStore,
        *,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        if not isinstance(runtime, DigitalTwinRuntime):
            raise TypeError("DevOps runtime must be a DigitalTwinRuntime")
        if not isinstance(provider, DevOpsEngineerProvider):
            raise TypeError("DevOps provider is invalid")
        if not isinstance(architecture_store, FileArchitectureArtifactStore):
            raise TypeError("DevOps architecture store is invalid")
        if not isinstance(engineering_store, FileEngineeringArtifactStore):
            raise TypeError("DevOps Engineering store is invalid")
        if not isinstance(qa_store, FileQAArtifactStore):
            raise TypeError("DevOps QA store is invalid")
        if not isinstance(security_store, FileSecurityArtifactStore):
            raise TypeError("DevOps Security store is invalid")
        if not isinstance(store, FileDevOpsArtifactStore):
            raise TypeError("DevOps artifact store is invalid")
        self._runtime = runtime
        self._provider = provider
        self._architecture_store = architecture_store
        self._engineering_store = engineering_store
        self._qa_store = qa_store
        self._security_store = security_store
        self._store = store
        self._clock = clock or (lambda: datetime.now(timezone.utc))

    def run(
        self,
        *,
        execution_id: str,
        twin: DigitalTwinDefinition,
        authority: DelegatedAuthority,
        work_order: DevOpsWorkOrder,
        architecture: ArchitectureProposalArtifact,
        engineering_artifacts: tuple[EngineeringWorkArtifact, ...],
        qa_artifact: QAWorkArtifact,
        security_artifact: SecurityWorkArtifact,
    ) -> DevOpsWorkArtifact:
        """Create or reopen one exact source-bound DevOps artifact."""

        self._validate_sources(
            work_order, architecture, engineering_artifacts, qa_artifact, security_artifact
        )
        objective = devops_objective(
            work_order, architecture, engineering_artifacts, qa_artifact, security_artifact
        )
        self._validate_profile(twin, authority, work_order, objective)
        assignment = self._assignment(
            work_order, architecture, engineering_artifacts, qa_artifact,
            security_artifact, twin, authority, objective,
        )
        receipt = self._runtime.execute(
            execution_id=execution_id, twin=twin, assignment=assignment, authority=authority
        )
        if receipt.status is not DigitalTwinExecutionStatus.SUCCEEDED:
            raise DevOpsWorkforcePolicyError(
                "DevOps execution did not produce a successful bounded output"
            )
        request = _provider_request(execution_id, twin, assignment, authority)
        if request.digest != receipt.request_digest:
            raise DevOpsWorkforcePolicyError(
                "DevOps receipt does not bind the rebuilt provider request"
            )
        result = self._provider.render(request)
        if result.output_digest != receipt.output_digest:
            raise DevOpsWorkforcePolicyError("DevOps output does not match the execution receipt")
        artifact = _artifact_from_output(
            result.output,
            work_order=work_order,
            architecture=architecture,
            engineering_artifacts=engineering_artifacts,
            qa_artifact=qa_artifact,
            security_artifact=security_artifact,
            execution_id=execution_id,
            twin=twin,
            assignment=assignment,
            authority=authority,
            receipt=receipt,
        )
        return self._store.save(artifact)

    def get(self, tenant_id: str, execution_id: str) -> DevOpsWorkArtifact:
        return self._store.load(tenant_id, execution_id)

    def _validate_sources(
        self,
        work_order: DevOpsWorkOrder,
        architecture: ArchitectureProposalArtifact,
        engineering_artifacts: tuple[EngineeringWorkArtifact, ...],
        qa_artifact: QAWorkArtifact,
        security_artifact: SecurityWorkArtifact,
    ) -> None:
        if (
            not isinstance(work_order, DevOpsWorkOrder)
            or not isinstance(architecture, ArchitectureProposalArtifact)
            or not isinstance(qa_artifact, QAWorkArtifact)
            or not isinstance(security_artifact, SecurityWorkArtifact)
            or not isinstance(engineering_artifacts, tuple)
            or len(engineering_artifacts) != 4
            or any(not isinstance(item, EngineeringWorkArtifact) for item in engineering_artifacts)
        ):
            raise DevOpsWorkforcePolicyError("DevOps sources are invalid")
        engineering_digests = tuple(item.digest for item in engineering_artifacts)
        qa_source_digests = tuple(item.artifact_digest for item in qa_artifact.sources)
        security_source_digests = tuple(item.artifact_digest for item in security_artifact.sources)
        if not (
            architecture.business_role is AgentRole.SOFTWARE_ARCHITECT
            and architecture.tenant_id == work_order.tenant_id == qa_artifact.tenant_id == security_artifact.tenant_id
            and architecture.opportunity_id == work_order.opportunity_id == qa_artifact.opportunity_id == security_artifact.opportunity_id
            and architecture.digest == work_order.architecture_artifact_digest == qa_artifact.architecture_artifact_digest == security_artifact.architecture_artifact_digest
            and architecture.status == ARCHITECTURE_STATUS == qa_artifact.architecture_status == security_artifact.architecture_status
            and architecture.pilot_status == PILOT_STATUS == qa_artifact.pilot_status == security_artifact.pilot_status
            and work_order.business_role is DEVOPS_ROLE
            and work_order.status == ASSIGNMENT_STATUS
            and work_order.pilot_status == PILOT_STATUS
            and tuple(item.business_role for item in engineering_artifacts) == ENGINEERING_ROLES
            and engineering_digests == work_order.engineering_artifact_digests == qa_source_digests == security_source_digests
            and qa_artifact.digest == work_order.qa_artifact_digest == security_artifact.qa_artifact_digest
            and qa_artifact.status == QA_STATUS == security_artifact.qa_status
            and security_artifact.digest == work_order.security_artifact_digest
            and security_artifact.status == SECURITY_STATUS
            and all(item.tenant_id == work_order.tenant_id for item in engineering_artifacts)
            and all(item.opportunity_id == work_order.opportunity_id for item in engineering_artifacts)
            and all(item.opportunity_digest == architecture.opportunity_digest for item in engineering_artifacts)
            and all(
                item.architecture_artifact_id == architecture.artifact_id
                and item.architecture_artifact_digest == architecture.digest
                and item.architecture_status == ARCHITECTURE_STATUS
                and item.status == ENGINEERING_STATUS
                and item.pilot_status == PILOT_STATUS
                for item in engineering_artifacts
            )
        ):
            raise DevOpsWorkforcePolicyError(
                "DevOps assignment requires the exact architecture, Engineering, QA, and Security sources"
            )
        if self._architecture_store.load(architecture.tenant_id, architecture.execution_id) != architecture:
            raise DevOpsWorkforcePolicyError("DevOps architecture source does not match persisted state")
        for source in engineering_artifacts:
            if self._engineering_store.load(source.tenant_id, source.execution_id) != source:
                raise DevOpsWorkforcePolicyError("DevOps Engineering source does not match persisted state")
        if self._qa_store.load(qa_artifact.tenant_id, qa_artifact.execution_id) != qa_artifact:
            raise DevOpsWorkforcePolicyError("DevOps QA source does not match persisted state")
        if self._security_store.load(security_artifact.tenant_id, security_artifact.execution_id) != security_artifact:
            raise DevOpsWorkforcePolicyError("DevOps Security source does not match persisted state")

    def _validate_profile(
        self,
        twin: DigitalTwinDefinition,
        authority: DelegatedAuthority,
        work_order: DevOpsWorkOrder,
        objective: str,
    ) -> None:
        if not isinstance(twin, DigitalTwinDefinition) or not isinstance(authority, DelegatedAuthority):
            raise DevOpsWorkforcePolicyError("DevOps authority is invalid")
        if not (
            twin.business_role is authority.business_role is work_order.business_role is DEVOPS_ROLE
            and twin.provider_id == self._provider.provider_id
            and twin.capability_ids == DEVOPS_CAPABILITIES
            and twin.approved_tool_ids == ()
            and authority.tenant_id == work_order.tenant_id
            and authority.assignment_id == work_order.assignment_id
            and authority.twin_id == twin.twin_id
            and authority.allowed_action_ids == DEVOPS_ACTIONS
            and authority.allowed_tool_ids == ()
            and authority.max_tool_calls == 0
            and not authority.live_provider_allowed
            and authority.issued_at <= work_order.issued_at <= authority.expires_at
            and authority.objective_digest == hashlib.sha256(objective.encode("utf-8")).hexdigest()
        ):
            raise DevOpsWorkforcePolicyError(
                "DevOps role, capability, authority, assignment, tool, or tenant boundary does not match"
            )

    def _assignment(
        self,
        work_order: DevOpsWorkOrder,
        architecture: ArchitectureProposalArtifact,
        engineering_artifacts: tuple[EngineeringWorkArtifact, ...],
        qa_artifact: QAWorkArtifact,
        security_artifact: SecurityWorkArtifact,
        twin: DigitalTwinDefinition,
        authority: DelegatedAuthority,
        objective: str,
    ) -> DigitalTwinAssignment:
        sources = tuple(
            {
                "artifact_digest": item.digest,
                "business_role": item.business_role.value,
                "interface_contract_ids": tuple(contract.contract_id for contract in item.interface_contracts),
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
            ContextValue("devops_role", work_order.business_role.value),
            ContextValue("opportunity_id", work_order.opportunity_id),
            ContextValue("opportunity_digest", architecture.opportunity_digest),
            ContextValue("opportunity_title", architecture.title),
            ContextValue("architecture_artifact_id", architecture.artifact_id),
            ContextValue("architecture_artifact_digest", architecture.digest),
            ContextValue("architecture_status", architecture.status),
            ContextValue("engineering_artifact_digests_json", _json(work_order.engineering_artifact_digests)),
            ContextValue("engineering_sources_json", _json(sources)),
            ContextValue("qa_artifact_id", qa_artifact.artifact_id),
            ContextValue("qa_execution_id", qa_artifact.execution_id),
            ContextValue("qa_artifact_digest", qa_artifact.digest),
            ContextValue("qa_status", qa_artifact.status),
            ContextValue("security_artifact_id", security_artifact.artifact_id),
            ContextValue("security_execution_id", security_artifact.execution_id),
            ContextValue("security_artifact_digest", security_artifact.digest),
            ContextValue("security_status", security_artifact.status),
            ContextValue("acceptance_checks_json", _json(work_order.acceptance_checks)),
            ContextValue("operational_risks_json", _json(work_order.operational_risks)),
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
            required_capability_ids=DEVOPS_CAPABILITIES,
            requested_tool_ids=(),
            authority_id=authority.authority_id,
            authority_digest=authority.digest,
            created_at=self._now(),
        )

    def _now(self) -> datetime:
        value = self._clock()
        if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("DevOps workforce clock must be timezone-aware")
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
    work_order: DevOpsWorkOrder,
    architecture: ArchitectureProposalArtifact,
    engineering_artifacts: tuple[EngineeringWorkArtifact, ...],
    qa_artifact: QAWorkArtifact,
    security_artifact: SecurityWorkArtifact,
    execution_id: str,
    twin: DigitalTwinDefinition,
    assignment: DigitalTwinAssignment,
    authority: DelegatedAuthority,
    receipt: DigitalTwinExecutionReceipt,
) -> DevOpsWorkArtifact:
    values = {item.key: item.value for item in output}
    expected = {
        "title", "summary", "ci_pipeline_json", "preview_environment_json",
        "migration_plan_json", "deployment_plan_json", "monitoring_plan_json",
        "rollback_plan_json", "coverage_requirements_json", "handoff_notes_json",
        "status_report_json", "source_states_json", "acceptance_checks_json",
    }
    if len(values) != len(output) or set(values) != expected:
        raise DevOpsWorkforcePolicyError("DevOps provider output is not closed")
    try:
        states = _closed_object(values["source_states_json"], {
            "artifact_status", "architecture_status", "engineering_status", "qa_status",
            "security_status", "execution_state", "pilot_status",
        })
        status = _closed_object(values["status_report_json"], {
            "state", "completed_items", "next_actions", "blockers", "escalations",
        })
        if not (
            states["artifact_status"] == ARTIFACT_STATUS
            and states["architecture_status"] == ARCHITECTURE_STATUS
            and states["engineering_status"] == ENGINEERING_STATUS
            and states["qa_status"] == QA_STATUS
            and states["security_status"] == SECURITY_STATUS
            and states["execution_state"] == EXECUTION_STATE
            and states["pilot_status"] == PILOT_STATUS
            and status["state"] == WORK_STATUS
        ):
            raise ValueError("DevOps provider output state changed")
        acceptance = _string_items(values["acceptance_checks_json"])
        if acceptance != work_order.acceptance_checks:
            raise ValueError("DevOps acceptance checks changed")
        sources = tuple(
            DevOpsEngineeringSource(
                artifact_id=item.artifact_id,
                execution_id=item.execution_id,
                business_role=item.business_role,
                artifact_digest=item.digest,
                architecture_artifact_digest=item.architecture_artifact_digest,
                target_component_ids=item.target_component_ids,
                interface_contract_ids=tuple(contract.contract_id for contract in item.interface_contracts),
                status=item.status,
                pilot_status=item.pilot_status,
            )
            for item in engineering_artifacts
        )
        ci = _closed_object(values["ci_pipeline_json"], {
            "plan_id", "source_engineering_artifact_digests", "qa_artifact_digest",
            "security_artifact_digest", "stages", "required_gates", "artifact_requirements",
            "failure_policy", "execution_state",
        })
        preview = _closed_object(values["preview_environment_json"], {
            "plan_id", "environment_class", "target_component_ids", "isolation_controls",
            "configuration_contract", "secret_reference_policy", "health_checks",
            "lifecycle_steps", "execution_state",
        })
        migration = _closed_object(values["migration_plan_json"], {
            "plan_id", "data_engineering_artifact_digest", "target_component_ids",
            "migration_scopes", "preflight_checks", "apply_steps", "verification_steps",
            "rollback_steps", "execution_state",
        })
        deployment = _closed_object(values["deployment_plan_json"], {
            "plan_id", "target_environment", "source_engineering_artifact_digests",
            "qa_artifact_digest", "security_artifact_digest", "prerequisites",
            "deployment_steps", "approval_gates", "evidence_requirements",
            "success_criteria", "execution_state",
        })
        monitoring = _closed_object(values["monitoring_plan_json"], {
            "plan_id", "target_environment", "signals", "alert_conditions",
            "dashboard_requirements", "evidence_requirements", "execution_state",
        })
        rollback = _closed_object(values["rollback_plan_json"], {
            "plan_id", "target_environment", "deployment_plan_id", "migration_plan_id",
            "triggers", "rollback_steps", "data_safety_controls", "verification_steps",
            "escalation_policy", "execution_state",
        })
        return DevOpsWorkArtifact(
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
            architecture_status=states["architecture_status"],
            sources=sources,
            qa_artifact_id=qa_artifact.artifact_id,
            qa_execution_id=qa_artifact.execution_id,
            qa_artifact_digest=qa_artifact.digest,
            qa_status=states["qa_status"],
            security_artifact_id=security_artifact.artifact_id,
            security_execution_id=security_artifact.execution_id,
            security_artifact_digest=security_artifact.digest,
            security_status=states["security_status"],
            capability_ids=DEVOPS_CAPABILITIES,
            action_ids=DEVOPS_ACTIONS,
            title=values["title"],
            summary=values["summary"],
            ci_pipeline=CIPipelinePlan(
                plan_id=ci["plan_id"],
                source_engineering_artifact_digests=_record_strings(ci, "source_engineering_artifact_digests"),
                qa_artifact_digest=ci["qa_artifact_digest"],
                security_artifact_digest=ci["security_artifact_digest"],
                stages=_record_strings(ci, "stages"),
                required_gates=_record_strings(ci, "required_gates"),
                artifact_requirements=_record_strings(ci, "artifact_requirements"),
                failure_policy=ci["failure_policy"],
                execution_state=ci["execution_state"],
            ),
            preview_environment=PreviewEnvironmentPlan(
                plan_id=preview["plan_id"], environment_class=preview["environment_class"],
                target_component_ids=_record_strings(preview, "target_component_ids"),
                isolation_controls=_record_strings(preview, "isolation_controls"),
                configuration_contract=_record_strings(preview, "configuration_contract"),
                secret_reference_policy=preview["secret_reference_policy"],
                health_checks=_record_strings(preview, "health_checks"),
                lifecycle_steps=_record_strings(preview, "lifecycle_steps"),
                execution_state=preview["execution_state"],
            ),
            migration_plan=MigrationPlan(
                plan_id=migration["plan_id"],
                data_engineering_artifact_digest=migration["data_engineering_artifact_digest"],
                target_component_ids=_record_strings(migration, "target_component_ids"),
                migration_scopes=_record_strings(migration, "migration_scopes"),
                preflight_checks=_record_strings(migration, "preflight_checks"),
                apply_steps=_record_strings(migration, "apply_steps"),
                verification_steps=_record_strings(migration, "verification_steps"),
                rollback_steps=_record_strings(migration, "rollback_steps"),
                execution_state=migration["execution_state"],
            ),
            deployment_plan=DeploymentPlan(
                plan_id=deployment["plan_id"], target_environment=deployment["target_environment"],
                source_engineering_artifact_digests=_record_strings(deployment, "source_engineering_artifact_digests"),
                qa_artifact_digest=deployment["qa_artifact_digest"],
                security_artifact_digest=deployment["security_artifact_digest"],
                prerequisites=_record_strings(deployment, "prerequisites"),
                deployment_steps=_record_strings(deployment, "deployment_steps"),
                approval_gates=_record_strings(deployment, "approval_gates"),
                evidence_requirements=_record_strings(deployment, "evidence_requirements"),
                success_criteria=_record_strings(deployment, "success_criteria"),
                execution_state=deployment["execution_state"],
            ),
            monitoring_plan=MonitoringPlan(
                plan_id=monitoring["plan_id"], target_environment=monitoring["target_environment"],
                signals=_record_strings(monitoring, "signals"),
                alert_conditions=_record_strings(monitoring, "alert_conditions"),
                dashboard_requirements=_record_strings(monitoring, "dashboard_requirements"),
                evidence_requirements=_record_strings(monitoring, "evidence_requirements"),
                execution_state=monitoring["execution_state"],
            ),
            rollback_plan=RollbackPlan(
                plan_id=rollback["plan_id"], target_environment=rollback["target_environment"],
                deployment_plan_id=rollback["deployment_plan_id"],
                migration_plan_id=rollback["migration_plan_id"],
                triggers=_record_strings(rollback, "triggers"),
                rollback_steps=_record_strings(rollback, "rollback_steps"),
                data_safety_controls=_record_strings(rollback, "data_safety_controls"),
                verification_steps=_record_strings(rollback, "verification_steps"),
                escalation_policy=rollback["escalation_policy"],
                execution_state=rollback["execution_state"],
            ),
            acceptance_checks=acceptance,
            coverage_requirements=_string_items(values["coverage_requirements_json"]),
            handoff_notes=_string_items(values["handoff_notes_json"]),
            status_report=DevOpsStatusReport(
                state=status["state"],
                completed_items=_object_strings(status, "completed_items"),
                next_actions=_object_strings(status, "next_actions"),
                blockers=_object_strings(status, "blockers"),
                escalations=_object_strings(status, "escalations"),
            ),
            authority_digest=authority.digest,
            assignment_digest=assignment.digest,
            request_digest=receipt.request_digest,
            output_digest=receipt.output_digest,
            receipt_digest=receipt.digest,
            generated_at=receipt.completed_at,
        )
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
        raise DevOpsWorkforcePolicyError("DevOps provider output failed typed validation") from error


def _closed_object(value: str, keys: set[str]) -> dict:
    decoded = json.loads(value)
    if not isinstance(decoded, dict) or set(decoded) != keys:
        raise ValueError("DevOps output object is invalid")
    return decoded


def _string_items(value: str) -> tuple[str, ...]:
    decoded = json.loads(value)
    if not isinstance(decoded, list) or any(not isinstance(item, str) for item in decoded):
        raise ValueError("DevOps output collection is invalid")
    return tuple(decoded)


def _record_strings(value: dict, key: str) -> tuple[str, ...]:
    items = value[key]
    if not isinstance(items, list) or any(not isinstance(item, str) for item in items):
        raise ValueError("DevOps nested collection is invalid")
    return tuple(items)


def _object_strings(value: dict, key: str) -> tuple[str, ...]:
    return _record_strings(value, key)


def _json(value: object) -> str:
    return json.dumps(value, separators=(",", ":"), ensure_ascii=False)
