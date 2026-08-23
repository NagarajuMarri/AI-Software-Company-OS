"""Governed source-bound composition for the ASCOS Day 27 Security Engineer."""

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
from runtime.workforce_security.errors import SecurityWorkforcePolicyError
from runtime.workforce_security.models import (
    ARCHITECTURE_STATUS,
    ARTIFACT_STATUS,
    ASSIGNMENT_STATUS,
    ENGINEERING_STATUS,
    FINDING_STATUS,
    PILOT_STATUS,
    QA_STATUS,
    SECURITY_ACTIONS,
    SECURITY_CAPABILITIES,
    SECURITY_ROLE,
    WORK_STATUS,
    DependencyCheckKind,
    DependencyCheckSpec,
    SecretCheckSpec,
    SecurityEngineeringSource,
    SecurityFinding,
    SecurityFindingKind,
    SecuritySeverity,
    SecurityStatusReport,
    SecurityThreat,
    SecurityWorkArtifact,
    SecurityWorkOrder,
    ThreatCategory,
    artifact_id_for,
)
from runtime.workforce_security.persistence import FileSecurityArtifactStore
from runtime.workforce_security.provider import SecurityEngineerProvider


def security_objective(
    work_order: SecurityWorkOrder,
    architecture: ArchitectureProposalArtifact,
    engineering_artifacts: tuple[EngineeringWorkArtifact, ...],
    qa_artifact: QAWorkArtifact,
) -> str:
    """Return the exact bounded objective for one Security planning assignment."""

    if not isinstance(work_order, SecurityWorkOrder) or not isinstance(
        architecture, ArchitectureProposalArtifact
    ):
        raise TypeError("Security objective source is invalid")
    if (
        not isinstance(engineering_artifacts, tuple)
        or any(not isinstance(item, EngineeringWorkArtifact) for item in engineering_artifacts)
        or not isinstance(qa_artifact, QAWorkArtifact)
    ):
        raise TypeError("Security workforce sources are invalid")
    source_digest = hashlib.sha256(
        "|".join(item.digest for item in engineering_artifacts).encode("utf-8")
    ).hexdigest()
    return (
        f"Execute bounded SECURITY_ENGINEER work order {work_order.work_order_id} "
        f"({work_order.digest}) against architecture {architecture.artifact_id} "
        f"({architecture.digest}), ordered Engineering source set ({source_digest}), and QA "
        f"artifact {qa_artifact.artifact_id} ({qa_artifact.digest}); produce a typed threat model, "
        "dependency and secret check specifications, and draft security findings only. Do not "
        "access a workspace, filesystem, repository, command, network, or credential; execute a "
        "scan; remediate; approve security or quality; perform DevOps, Documentation, or "
        "orchestration work; merge, deploy, release, accept risk, or select a pilot."
    )


class SecurityWorkforceService:
    """Execute the Security profile through one fail-closed runtime boundary."""

    def __init__(
        self,
        runtime: DigitalTwinRuntime,
        provider: SecurityEngineerProvider,
        architecture_store: FileArchitectureArtifactStore,
        engineering_store: FileEngineeringArtifactStore,
        qa_store: FileQAArtifactStore,
        store: FileSecurityArtifactStore,
        *,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        if not isinstance(runtime, DigitalTwinRuntime):
            raise TypeError("Security runtime must be a DigitalTwinRuntime")
        if not isinstance(provider, SecurityEngineerProvider):
            raise TypeError("Security provider is invalid")
        if not isinstance(architecture_store, FileArchitectureArtifactStore):
            raise TypeError("Security architecture store is invalid")
        if not isinstance(engineering_store, FileEngineeringArtifactStore):
            raise TypeError("Security Engineering store is invalid")
        if not isinstance(qa_store, FileQAArtifactStore):
            raise TypeError("Security QA store is invalid")
        if not isinstance(store, FileSecurityArtifactStore):
            raise TypeError("Security artifact store is invalid")
        self._runtime = runtime
        self._provider = provider
        self._architecture_store = architecture_store
        self._engineering_store = engineering_store
        self._qa_store = qa_store
        self._store = store
        self._clock = clock or (lambda: datetime.now(timezone.utc))

    def run(
        self,
        *,
        execution_id: str,
        twin: DigitalTwinDefinition,
        authority: DelegatedAuthority,
        work_order: SecurityWorkOrder,
        architecture: ArchitectureProposalArtifact,
        engineering_artifacts: tuple[EngineeringWorkArtifact, ...],
        qa_artifact: QAWorkArtifact,
    ) -> SecurityWorkArtifact:
        """Create or reopen one exact source-bound Security artifact."""

        self._validate_sources(work_order, architecture, engineering_artifacts, qa_artifact)
        objective = security_objective(
            work_order, architecture, engineering_artifacts, qa_artifact
        )
        self._validate_profile(twin, authority, work_order, objective)
        assignment = self._assignment(
            work_order,
            architecture,
            engineering_artifacts,
            qa_artifact,
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
            raise SecurityWorkforcePolicyError(
                "Security execution did not produce a successful bounded output"
            )
        request = _provider_request(execution_id, twin, assignment, authority)
        if request.digest != receipt.request_digest:
            raise SecurityWorkforcePolicyError(
                "Security receipt does not bind the rebuilt provider request"
            )
        result = self._provider.render(request)
        if result.output_digest != receipt.output_digest:
            raise SecurityWorkforcePolicyError(
                "Security output does not match the execution receipt"
            )
        artifact = _artifact_from_output(
            result.output,
            work_order=work_order,
            architecture=architecture,
            engineering_artifacts=engineering_artifacts,
            qa_artifact=qa_artifact,
            execution_id=execution_id,
            twin=twin,
            assignment=assignment,
            authority=authority,
            receipt=receipt,
        )
        return self._store.save(artifact)

    def get(self, tenant_id: str, execution_id: str) -> SecurityWorkArtifact:
        return self._store.load(tenant_id, execution_id)

    def _validate_sources(
        self,
        work_order: SecurityWorkOrder,
        architecture: ArchitectureProposalArtifact,
        engineering_artifacts: tuple[EngineeringWorkArtifact, ...],
        qa_artifact: QAWorkArtifact,
    ) -> None:
        if (
            not isinstance(work_order, SecurityWorkOrder)
            or not isinstance(architecture, ArchitectureProposalArtifact)
            or not isinstance(qa_artifact, QAWorkArtifact)
            or not isinstance(engineering_artifacts, tuple)
            or len(engineering_artifacts) != 4
            or any(not isinstance(item, EngineeringWorkArtifact) for item in engineering_artifacts)
        ):
            raise SecurityWorkforcePolicyError("Security sources are invalid")
        engineering_digests = tuple(item.digest for item in engineering_artifacts)
        qa_source_digests = tuple(item.artifact_digest for item in qa_artifact.sources)
        if not (
            architecture.business_role is AgentRole.SOFTWARE_ARCHITECT
            and architecture.tenant_id == work_order.tenant_id == qa_artifact.tenant_id
            and architecture.opportunity_id
            == work_order.opportunity_id
            == qa_artifact.opportunity_id
            and architecture.digest
            == work_order.architecture_artifact_digest
            == qa_artifact.architecture_artifact_digest
            and architecture.status == ARCHITECTURE_STATUS == qa_artifact.architecture_status
            and architecture.pilot_status == PILOT_STATUS == qa_artifact.pilot_status
            and work_order.business_role is SECURITY_ROLE
            and work_order.status == ASSIGNMENT_STATUS
            and work_order.pilot_status == PILOT_STATUS
            and tuple(item.business_role for item in engineering_artifacts) == ENGINEERING_ROLES
            and engineering_digests
            == work_order.engineering_artifact_digests
            == qa_source_digests
            and qa_artifact.digest == work_order.qa_artifact_digest
            and qa_artifact.status == QA_STATUS
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
            raise SecurityWorkforcePolicyError(
                "Security assignment requires the exact architecture, Engineering, and QA sources"
            )
        if self._architecture_store.load(
            architecture.tenant_id, architecture.execution_id
        ) != architecture:
            raise SecurityWorkforcePolicyError(
                "Security architecture source does not match persisted state"
            )
        for source in engineering_artifacts:
            if self._engineering_store.load(source.tenant_id, source.execution_id) != source:
                raise SecurityWorkforcePolicyError(
                    "Security Engineering source does not match persisted state"
                )
        if self._qa_store.load(qa_artifact.tenant_id, qa_artifact.execution_id) != qa_artifact:
            raise SecurityWorkforcePolicyError(
                "Security QA source does not match persisted state"
            )

    def _validate_profile(
        self,
        twin: DigitalTwinDefinition,
        authority: DelegatedAuthority,
        work_order: SecurityWorkOrder,
        objective: str,
    ) -> None:
        if not isinstance(twin, DigitalTwinDefinition) or not isinstance(
            authority, DelegatedAuthority
        ):
            raise SecurityWorkforcePolicyError("Security authority is invalid")
        if not (
            twin.business_role
            is authority.business_role
            is work_order.business_role
            is SECURITY_ROLE
            and twin.provider_id == self._provider.provider_id
            and twin.capability_ids == SECURITY_CAPABILITIES
            and twin.approved_tool_ids == ()
            and authority.tenant_id == work_order.tenant_id
            and authority.assignment_id == work_order.assignment_id
            and authority.twin_id == twin.twin_id
            and authority.allowed_action_ids == SECURITY_ACTIONS
            and authority.allowed_tool_ids == ()
            and authority.max_tool_calls == 0
            and not authority.live_provider_allowed
            and authority.issued_at <= work_order.issued_at <= authority.expires_at
            and authority.objective_digest
            == hashlib.sha256(objective.encode("utf-8")).hexdigest()
        ):
            raise SecurityWorkforcePolicyError(
                "Security role, capability, authority, assignment, tool, or tenant boundary does not match"
            )

    def _assignment(
        self,
        work_order: SecurityWorkOrder,
        architecture: ArchitectureProposalArtifact,
        engineering_artifacts: tuple[EngineeringWorkArtifact, ...],
        qa_artifact: QAWorkArtifact,
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
            ContextValue("security_role", work_order.business_role.value),
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
            ContextValue("qa_artifact_id", qa_artifact.artifact_id),
            ContextValue("qa_execution_id", qa_artifact.execution_id),
            ContextValue("qa_artifact_digest", qa_artifact.digest),
            ContextValue("qa_status", qa_artifact.status),
            ContextValue("acceptance_checks_json", _json(work_order.acceptance_checks)),
            ContextValue("security_risks_json", _json(work_order.security_risks)),
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
            required_capability_ids=SECURITY_CAPABILITIES,
            requested_tool_ids=(),
            authority_id=authority.authority_id,
            authority_digest=authority.digest,
            created_at=self._now(),
        )

    def _now(self) -> datetime:
        value = self._clock()
        if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("Security workforce clock must be timezone-aware")
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
    work_order: SecurityWorkOrder,
    architecture: ArchitectureProposalArtifact,
    engineering_artifacts: tuple[EngineeringWorkArtifact, ...],
    qa_artifact: QAWorkArtifact,
    execution_id: str,
    twin: DigitalTwinDefinition,
    assignment: DigitalTwinAssignment,
    authority: DelegatedAuthority,
    receipt: DigitalTwinExecutionReceipt,
) -> SecurityWorkArtifact:
    values = {item.key: item.value for item in output}
    expected = {
        "title",
        "summary",
        "threat_spoofing_json",
        "threat_tampering_json",
        "threat_repudiation_json",
        "threat_disclosure_json",
        "threat_denial_json",
        "threat_elevation_json",
        "dependency_backend_json",
        "dependency_frontend_json",
        "dependency_ai_json",
        "dependency_data_json",
        "exposure_check_backend_json",
        "exposure_check_frontend_json",
        "exposure_check_ai_json",
        "exposure_check_data_json",
        "finding_authority_json",
        "finding_dependency_json",
        "finding_exposure_json",
        "coverage_requirements_json",
        "handoff_notes_json",
        "status_report_json",
        "source_states_json",
        "acceptance_checks_json",
    }
    if len(values) != len(output) or set(values) != expected:
        raise SecurityWorkforcePolicyError("Security provider output is not closed")
    try:
        states = _closed_object(
            values["source_states_json"],
            {
                "artifact_status",
                "architecture_status",
                "engineering_status",
                "qa_status",
                "finding_status",
                "pilot_status",
            },
        )
        status = _closed_object(
            values["status_report_json"],
            {"state", "completed_items", "next_actions", "blockers", "escalations"},
        )
        if not (
            states["artifact_status"] == ARTIFACT_STATUS
            and states["architecture_status"] == ARCHITECTURE_STATUS
            and states["engineering_status"] == ENGINEERING_STATUS
            and states["qa_status"] == QA_STATUS
            and states["finding_status"] == FINDING_STATUS
            and states["pilot_status"] == PILOT_STATUS
            and status["state"] == WORK_STATUS
        ):
            raise ValueError("Security provider output state changed")
        acceptance = _string_items(values["acceptance_checks_json"])
        if acceptance != work_order.acceptance_checks:
            raise ValueError("Security acceptance checks changed")
        sources = tuple(
            SecurityEngineeringSource(
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
        return SecurityWorkArtifact(
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
            capability_ids=SECURITY_CAPABILITIES,
            action_ids=SECURITY_ACTIONS,
            title=values["title"],
            summary=values["summary"],
            threats=_threats(
                values["threat_spoofing_json"],
                values["threat_tampering_json"],
                values["threat_repudiation_json"],
                values["threat_disclosure_json"],
                values["threat_denial_json"],
                values["threat_elevation_json"],
            ),
            dependency_checks=_dependency_checks(
                values["dependency_backend_json"],
                values["dependency_frontend_json"],
                values["dependency_ai_json"],
                values["dependency_data_json"],
            ),
            secret_checks=_secret_checks(
                values["exposure_check_backend_json"],
                values["exposure_check_frontend_json"],
                values["exposure_check_ai_json"],
                values["exposure_check_data_json"],
            ),
            findings=_findings(
                values["finding_authority_json"],
                values["finding_dependency_json"],
                values["finding_exposure_json"],
            ),
            acceptance_checks=acceptance,
            coverage_requirements=_string_items(values["coverage_requirements_json"]),
            handoff_notes=_string_items(values["handoff_notes_json"]),
            status_report=SecurityStatusReport(
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
        raise SecurityWorkforcePolicyError(
            "Security provider output failed typed validation"
        ) from error


def _threats(*values: str) -> tuple[SecurityThreat, ...]:
    keys = {
        "threat_id", "category", "source_engineering_artifact_digests",
        "target_component_ids", "asset", "trust_boundary", "scenario",
        "security_properties", "mitigations", "residual_risk", "validation_state",
    }
    return tuple(
        SecurityThreat(
            threat_id=item["threat_id"],
            category=ThreatCategory(item["category"]),
            source_engineering_artifact_digests=_record_strings(item, "source_engineering_artifact_digests"),
            target_component_ids=_record_strings(item, "target_component_ids"),
            asset=item["asset"],
            trust_boundary=item["trust_boundary"],
            scenario=item["scenario"],
            security_properties=_record_strings(item, "security_properties"),
            mitigations=_record_strings(item, "mitigations"),
            residual_risk=item["residual_risk"],
            validation_state=item["validation_state"],
        )
        for value in values
        for item in _records(value, keys)
    )


def _dependency_checks(*values: str) -> tuple[DependencyCheckSpec, ...]:
    keys = {
        "check_id", "kind", "source_engineering_artifact_digest",
        "target_component_ids", "manifest_scope", "required_checks",
        "failure_threshold", "expected_evidence", "execution_state",
    }
    return tuple(
        DependencyCheckSpec(
            check_id=item["check_id"],
            kind=DependencyCheckKind(item["kind"]),
            source_engineering_artifact_digest=item["source_engineering_artifact_digest"],
            target_component_ids=_record_strings(item, "target_component_ids"),
            manifest_scope=item["manifest_scope"],
            required_checks=_record_strings(item, "required_checks"),
            failure_threshold=SecuritySeverity(item["failure_threshold"]),
            expected_evidence=_record_strings(item, "expected_evidence"),
            execution_state=item["execution_state"],
        )
        for value in values
        for item in _records(value, keys)
    )


def _secret_checks(*values: str) -> tuple[SecretCheckSpec, ...]:
    keys = {
        "check_id", "source_engineering_artifact_digest", "target_component_ids",
        "search_scopes", "detector_classes", "allowlist_policy", "incident_response",
        "expected_evidence", "execution_state",
    }
    return tuple(
        SecretCheckSpec(
            check_id=item["check_id"],
            source_engineering_artifact_digest=item["source_engineering_artifact_digest"],
            target_component_ids=_record_strings(item, "target_component_ids"),
            search_scopes=_record_strings(item, "search_scopes"),
            detector_classes=_record_strings(item, "detector_classes"),
            allowlist_policy=item["allowlist_policy"],
            incident_response=item["incident_response"],
            expected_evidence=_record_strings(item, "expected_evidence"),
            execution_state=item["execution_state"],
        )
        for value in values
        for item in _records(value, keys)
    )


def _findings(*values: str) -> tuple[SecurityFinding, ...]:
    keys = {
        "finding_id", "kind", "severity", "source_engineering_artifact_digests",
        "qa_artifact_digest", "title", "evidence_basis", "risk", "recommendation",
        "verification_requirements", "status",
    }
    return tuple(
        SecurityFinding(
            finding_id=item["finding_id"],
            kind=SecurityFindingKind(item["kind"]),
            severity=SecuritySeverity(item["severity"]),
            source_engineering_artifact_digests=_record_strings(
                item, "source_engineering_artifact_digests"
            ),
            qa_artifact_digest=item["qa_artifact_digest"],
            title=item["title"],
            evidence_basis=item["evidence_basis"],
            risk=item["risk"],
            recommendation=item["recommendation"],
            verification_requirements=_record_strings(item, "verification_requirements"),
            status=item["status"],
        )
        for value in values
        for item in _records(value, keys)
    )


def _records(value: str, keys: set[str]) -> tuple[dict, ...]:
    decoded = json.loads(value)
    if not isinstance(decoded, list) or any(
        not isinstance(item, dict) or set(item) != keys for item in decoded
    ):
        raise ValueError("Security structured output is invalid")
    return tuple(decoded)


def _string_items(value: str) -> tuple[str, ...]:
    decoded = json.loads(value)
    if not isinstance(decoded, list) or any(not isinstance(item, str) for item in decoded):
        raise ValueError("Security output collection is invalid")
    return tuple(decoded)


def _record_strings(value: dict, key: str) -> tuple[str, ...]:
    items = value[key]
    if not isinstance(items, list) or any(not isinstance(item, str) for item in items):
        raise ValueError("Security nested collection is invalid")
    return tuple(items)


def _closed_object(value: str, keys: set[str]) -> dict:
    decoded = json.loads(value)
    if not isinstance(decoded, dict) or set(decoded) != keys:
        raise ValueError("Security output object is invalid")
    return decoded


def _object_strings(value: dict, key: str) -> tuple[str, ...]:
    items = value[key]
    if not isinstance(items, list) or any(not isinstance(item, str) for item in items):
        raise ValueError("Security output object collection is invalid")
    return tuple(items)


def _json(value: object) -> str:
    return json.dumps(value, separators=(",", ":"), ensure_ascii=False)
