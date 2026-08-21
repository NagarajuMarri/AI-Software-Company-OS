"""Governed source-bound composition for the ASCOS Day 29 Documentation Engineer."""

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
from runtime.workforce_devops import DevOpsWorkArtifact, FileDevOpsArtifactStore
from runtime.workforce_engineering import (
    ENGINEERING_ROLES,
    EngineeringWorkArtifact,
    FileEngineeringArtifactStore,
)
from runtime.workforce_qa import FileQAArtifactStore, QAWorkArtifact
from runtime.workforce_security import FileSecurityArtifactStore, SecurityWorkArtifact
from runtime.workforce_documentation.errors import DocumentationWorkforcePolicyError
from runtime.workforce_documentation.models import (
    ARCHITECTURE_STATUS,
    ARTIFACT_STATUS,
    ASSIGNMENT_STATUS,
    DEVOPS_STATUS,
    DOCUMENTATION_ACTIONS,
    DOCUMENTATION_CAPABILITIES,
    DOCUMENTATION_ROLE,
    DOCUMENT_STATUS,
    ENGINEERING_STATUS,
    PILOT_STATUS,
    PUBLICATION_STATE,
    QA_STATUS,
    SECURITY_STATUS,
    VALIDATION_STATE,
    WORK_STATUS,
    CustomerHandoff,
    DocumentationEngineeringSource,
    DocumentationKind,
    DocumentationRecord,
    DocumentationSection,
    DocumentationStatusReport,
    DocumentationWorkArtifact,
    DocumentationWorkOrder,
    artifact_id_for,
)
from runtime.workforce_documentation.persistence import FileDocumentationArtifactStore
from runtime.workforce_documentation.provider import DocumentationEngineerProvider


def documentation_objective(
    work_order: DocumentationWorkOrder,
    architecture: ArchitectureProposalArtifact,
    engineering_artifacts: tuple[EngineeringWorkArtifact, ...],
    qa_artifact: QAWorkArtifact,
    security_artifact: SecurityWorkArtifact,
    devops_artifact: DevOpsWorkArtifact,
) -> str:
    """Return the exact bounded objective for one documentation assignment."""

    if not isinstance(work_order, DocumentationWorkOrder) or not isinstance(
        architecture, ArchitectureProposalArtifact
    ):
        raise TypeError("Documentation objective source is invalid")
    if (
        not isinstance(engineering_artifacts, tuple)
        or any(not isinstance(item, EngineeringWorkArtifact) for item in engineering_artifacts)
        or not isinstance(qa_artifact, QAWorkArtifact)
        or not isinstance(security_artifact, SecurityWorkArtifact)
        or not isinstance(devops_artifact, DevOpsWorkArtifact)
    ):
        raise TypeError("Documentation workforce sources are invalid")
    source_digest = hashlib.sha256(
        "|".join(item.digest for item in engineering_artifacts).encode()
    ).hexdigest()
    return (
        f"Execute bounded DOCUMENTATION_ENGINEER work order {work_order.work_order_id} "
        f"({work_order.digest}) against Architecture {architecture.artifact_id} "
        f"({architecture.digest}), ordered Engineering source set ({source_digest}), QA "
        f"artifact {qa_artifact.artifact_id} ({qa_artifact.digest}), Security artifact "
        f"{security_artifact.artifact_id} ({security_artifact.digest}), and DevOps artifact "
        f"{devops_artifact.artifact_id} ({devops_artifact.digest}); produce typed technical, "
        "user, API, operations, release, validation, and customer-handoff drafts only. Do not "
        "access or modify a workspace, filesystem, repository, command, network, credential, "
        "customer channel, deployment, or release target; publish documentation; claim product "
        "execution; approve architecture, QA, Security, DevOps, or release; select a pilot; or "
        "perform multi-agent orchestration."
    )


class DocumentationWorkforceService:
    """Execute the Documentation profile through one fail-closed runtime boundary."""

    def __init__(
        self,
        runtime: DigitalTwinRuntime,
        provider: DocumentationEngineerProvider,
        architecture_store: FileArchitectureArtifactStore,
        engineering_store: FileEngineeringArtifactStore,
        qa_store: FileQAArtifactStore,
        security_store: FileSecurityArtifactStore,
        devops_store: FileDevOpsArtifactStore,
        store: FileDocumentationArtifactStore,
        *,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        expected = (
            (runtime, DigitalTwinRuntime, "runtime"),
            (provider, DocumentationEngineerProvider, "provider"),
            (architecture_store, FileArchitectureArtifactStore, "architecture store"),
            (engineering_store, FileEngineeringArtifactStore, "Engineering store"),
            (qa_store, FileQAArtifactStore, "QA store"),
            (security_store, FileSecurityArtifactStore, "Security store"),
            (devops_store, FileDevOpsArtifactStore, "DevOps store"),
            (store, FileDocumentationArtifactStore, "artifact store"),
        )
        for value, kind, label in expected:
            if not isinstance(value, kind):
                raise TypeError(f"Documentation {label} is invalid")
        self._runtime = runtime
        self._provider = provider
        self._architecture_store = architecture_store
        self._engineering_store = engineering_store
        self._qa_store = qa_store
        self._security_store = security_store
        self._devops_store = devops_store
        self._store = store
        self._clock = clock or (lambda: datetime.now(timezone.utc))

    def run(
        self,
        *,
        execution_id: str,
        twin: DigitalTwinDefinition,
        authority: DelegatedAuthority,
        work_order: DocumentationWorkOrder,
        architecture: ArchitectureProposalArtifact,
        engineering_artifacts: tuple[EngineeringWorkArtifact, ...],
        qa_artifact: QAWorkArtifact,
        security_artifact: SecurityWorkArtifact,
        devops_artifact: DevOpsWorkArtifact,
    ) -> DocumentationWorkArtifact:
        """Create or reopen one exact source-bound Documentation artifact."""

        self._validate_sources(
            work_order, architecture, engineering_artifacts, qa_artifact,
            security_artifact, devops_artifact,
        )
        objective = documentation_objective(
            work_order, architecture, engineering_artifacts, qa_artifact,
            security_artifact, devops_artifact,
        )
        self._validate_profile(twin, authority, work_order, objective)
        assignment = self._assignment(
            work_order, architecture, engineering_artifacts, qa_artifact,
            security_artifact, devops_artifact, twin, authority, objective,
        )
        receipt = self._runtime.execute(
            execution_id=execution_id, twin=twin, assignment=assignment, authority=authority
        )
        if receipt.status is not DigitalTwinExecutionStatus.SUCCEEDED:
            raise DocumentationWorkforcePolicyError(
                "Documentation execution did not produce a successful bounded output"
            )
        request = _provider_request(execution_id, twin, assignment, authority)
        if request.digest != receipt.request_digest:
            raise DocumentationWorkforcePolicyError(
                "Documentation receipt does not bind the rebuilt provider request"
            )
        result = self._provider.render(request)
        if result.output_digest != receipt.output_digest:
            raise DocumentationWorkforcePolicyError(
                "Documentation output does not match the execution receipt"
            )
        artifact = _artifact_from_output(
            result.output, work_order=work_order, architecture=architecture,
            engineering_artifacts=engineering_artifacts, qa_artifact=qa_artifact,
            security_artifact=security_artifact, devops_artifact=devops_artifact,
            execution_id=execution_id, twin=twin, assignment=assignment,
            authority=authority, receipt=receipt,
        )
        return self._store.save(artifact)

    def get(self, tenant_id: str, execution_id: str) -> DocumentationWorkArtifact:
        return self._store.load(tenant_id, execution_id)

    def _validate_sources(
        self,
        work_order: DocumentationWorkOrder,
        architecture: ArchitectureProposalArtifact,
        engineering_artifacts: tuple[EngineeringWorkArtifact, ...],
        qa_artifact: QAWorkArtifact,
        security_artifact: SecurityWorkArtifact,
        devops_artifact: DevOpsWorkArtifact,
    ) -> None:
        if (
            not isinstance(work_order, DocumentationWorkOrder)
            or not isinstance(architecture, ArchitectureProposalArtifact)
            or not isinstance(qa_artifact, QAWorkArtifact)
            or not isinstance(security_artifact, SecurityWorkArtifact)
            or not isinstance(devops_artifact, DevOpsWorkArtifact)
            or not isinstance(engineering_artifacts, tuple)
            or len(engineering_artifacts) != 4
            or any(not isinstance(item, EngineeringWorkArtifact) for item in engineering_artifacts)
        ):
            raise DocumentationWorkforcePolicyError("Documentation sources are invalid")
        engineering_digests = tuple(item.digest for item in engineering_artifacts)
        tenant_ids = {
            work_order.tenant_id, architecture.tenant_id, qa_artifact.tenant_id,
            security_artifact.tenant_id, devops_artifact.tenant_id,
            *(item.tenant_id for item in engineering_artifacts),
        }
        opportunity_ids = {
            work_order.opportunity_id, architecture.opportunity_id, qa_artifact.opportunity_id,
            security_artifact.opportunity_id, devops_artifact.opportunity_id,
            *(item.opportunity_id for item in engineering_artifacts),
        }
        if not (
            len(tenant_ids) == len(opportunity_ids) == 1
            and architecture.business_role is AgentRole.SOFTWARE_ARCHITECT
            and architecture.digest == work_order.architecture_artifact_digest
            == qa_artifact.architecture_artifact_digest
            == security_artifact.architecture_artifact_digest
            == devops_artifact.architecture_artifact_digest
            and architecture.status == ARCHITECTURE_STATUS
            == qa_artifact.architecture_status == security_artifact.architecture_status
            == devops_artifact.architecture_status
            and architecture.pilot_status == PILOT_STATUS == qa_artifact.pilot_status
            == security_artifact.pilot_status == devops_artifact.pilot_status
            and work_order.business_role is DOCUMENTATION_ROLE
            and work_order.status == ASSIGNMENT_STATUS
            and work_order.pilot_status == PILOT_STATUS
            and tuple(item.business_role for item in engineering_artifacts) == ENGINEERING_ROLES
            and engineering_digests == work_order.engineering_artifact_digests
            == tuple(item.artifact_digest for item in qa_artifact.sources)
            == tuple(item.artifact_digest for item in security_artifact.sources)
            == tuple(item.artifact_digest for item in devops_artifact.sources)
            and qa_artifact.digest == work_order.qa_artifact_digest
            == security_artifact.qa_artifact_digest == devops_artifact.qa_artifact_digest
            and qa_artifact.status == QA_STATUS == security_artifact.qa_status
            == devops_artifact.qa_status
            and security_artifact.digest == work_order.security_artifact_digest
            == devops_artifact.security_artifact_digest
            and security_artifact.status == SECURITY_STATUS == devops_artifact.security_status
            and devops_artifact.digest == work_order.devops_artifact_digest
            and devops_artifact.status == DEVOPS_STATUS
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
            raise DocumentationWorkforcePolicyError(
                "Documentation assignment requires the exact Architecture, Engineering, QA, Security, and DevOps sources"
            )
        persisted = (
            self._architecture_store.load(architecture.tenant_id, architecture.execution_id) == architecture
            and self._qa_store.load(qa_artifact.tenant_id, qa_artifact.execution_id) == qa_artifact
            and self._security_store.load(security_artifact.tenant_id, security_artifact.execution_id) == security_artifact
            and self._devops_store.load(devops_artifact.tenant_id, devops_artifact.execution_id) == devops_artifact
            and all(
                self._engineering_store.load(item.tenant_id, item.execution_id) == item
                for item in engineering_artifacts
            )
        )
        if not persisted:
            raise DocumentationWorkforcePolicyError(
                "Documentation sources do not match persisted state"
            )

    def _validate_profile(
        self, twin: DigitalTwinDefinition, authority: DelegatedAuthority,
        work_order: DocumentationWorkOrder, objective: str,
    ) -> None:
        if not isinstance(twin, DigitalTwinDefinition) or not isinstance(
            authority, DelegatedAuthority
        ):
            raise DocumentationWorkforcePolicyError("Documentation authority is invalid")
        if not (
            twin.business_role is authority.business_role is work_order.business_role is DOCUMENTATION_ROLE
            and twin.provider_id == self._provider.provider_id
            and twin.capability_ids == DOCUMENTATION_CAPABILITIES
            and twin.approved_tool_ids == ()
            and authority.tenant_id == work_order.tenant_id
            and authority.assignment_id == work_order.assignment_id
            and authority.twin_id == twin.twin_id
            and authority.allowed_action_ids == DOCUMENTATION_ACTIONS
            and authority.allowed_tool_ids == ()
            and authority.max_tool_calls == 0
            and not authority.live_provider_allowed
            and authority.issued_at <= work_order.issued_at <= authority.expires_at
            and authority.objective_digest == hashlib.sha256(objective.encode()).hexdigest()
        ):
            raise DocumentationWorkforcePolicyError(
                "Documentation role, capability, authority, assignment, tool, or tenant boundary does not match"
            )

    def _assignment(
        self, work_order: DocumentationWorkOrder, architecture: ArchitectureProposalArtifact,
        engineering_artifacts: tuple[EngineeringWorkArtifact, ...], qa_artifact: QAWorkArtifact,
        security_artifact: SecurityWorkArtifact, devops_artifact: DevOpsWorkArtifact,
        twin: DigitalTwinDefinition, authority: DelegatedAuthority, objective: str,
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
            ContextValue("documentation_role", work_order.business_role.value),
            ContextValue("opportunity_id", work_order.opportunity_id),
            ContextValue("opportunity_digest", architecture.opportunity_digest),
            ContextValue("opportunity_title", architecture.title),
            ContextValue("architecture_artifact_id", architecture.artifact_id),
            ContextValue("architecture_artifact_digest", architecture.digest),
            ContextValue("architecture_status", architecture.status),
            ContextValue("engineering_artifact_digests_json", _json(work_order.engineering_artifact_digests)),
            ContextValue("engineering_sources_json", _json(sources)),
            ContextValue("qa_artifact_id", qa_artifact.artifact_id),
            ContextValue("qa_artifact_digest", qa_artifact.digest),
            ContextValue("qa_status", qa_artifact.status),
            ContextValue("security_artifact_id", security_artifact.artifact_id),
            ContextValue("security_artifact_digest", security_artifact.digest),
            ContextValue("security_status", security_artifact.status),
            ContextValue("devops_artifact_id", devops_artifact.artifact_id),
            ContextValue("devops_artifact_digest", devops_artifact.digest),
            ContextValue("devops_status", devops_artifact.status),
            ContextValue("acceptance_checks_json", _json(work_order.acceptance_checks)),
            ContextValue("documentation_risks_json", _json(work_order.documentation_risks)),
            ContextValue("constraints_json", _json(work_order.constraints)),
            ContextValue("pilot_status", work_order.pilot_status),
        )
        return DigitalTwinAssignment(
            assignment_id=work_order.assignment_id, tenant_id=work_order.tenant_id,
            twin_id=twin.twin_id, business_role=work_order.business_role,
            objective=objective, context=context,
            required_capability_ids=DOCUMENTATION_CAPABILITIES, requested_tool_ids=(),
            authority_id=authority.authority_id, authority_digest=authority.digest,
            created_at=self._now(),
        )

    def _now(self) -> datetime:
        value = self._clock()
        if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("Documentation workforce clock must be timezone-aware")
        return value.astimezone(timezone.utc)


def _provider_request(
    execution_id: str, twin: DigitalTwinDefinition,
    assignment: DigitalTwinAssignment, authority: DelegatedAuthority,
) -> ProviderExecutionRequest:
    return ProviderExecutionRequest(
        execution_id=execution_id, provider_id=twin.provider_id, twin_id=twin.twin_id,
        twin_digest=twin.digest, assignment_id=assignment.assignment_id,
        assignment_digest=assignment.digest, authority_id=authority.authority_id,
        authority_digest=authority.digest, tenant_id=assignment.tenant_id,
        business_role=assignment.business_role, objective=assignment.objective,
        context=assignment.context, required_capability_ids=assignment.required_capability_ids,
        allowed_action_ids=authority.allowed_action_ids,
        allowed_tool_ids=assignment.requested_tool_ids,
        authority_expires_at=authority.expires_at, max_tool_calls=authority.max_tool_calls,
        max_output_bytes=authority.max_output_bytes,
    )


def _artifact_from_output(
    output: tuple[ContextValue, ...], *, work_order: DocumentationWorkOrder,
    architecture: ArchitectureProposalArtifact,
    engineering_artifacts: tuple[EngineeringWorkArtifact, ...], qa_artifact: QAWorkArtifact,
    security_artifact: SecurityWorkArtifact, devops_artifact: DevOpsWorkArtifact,
    execution_id: str, twin: DigitalTwinDefinition, assignment: DigitalTwinAssignment,
    authority: DelegatedAuthority, receipt: DigitalTwinExecutionReceipt,
) -> DocumentationWorkArtifact:
    values = {item.key: item.value for item in output}
    expected = {
        "title", "summary", "technical_document_json", "user_document_json",
        "api_document_json", "operations_document_json", "release_document_json",
        "customer_handoff_json",
        "coverage_requirements_json", "status_report_json", "source_states_json",
        "acceptance_checks_json",
    }
    if len(values) != len(output) or set(values) != expected:
        raise DocumentationWorkforcePolicyError("Documentation provider output is not closed")
    try:
        states = _closed_object(values["source_states_json"], {
            "artifact_status", "architecture_status", "engineering_status", "qa_status",
            "security_status", "devops_status", "document_status", "validation_state",
            "publication_state", "pilot_status",
        })
        if states != {
            "artifact_status": ARTIFACT_STATUS, "architecture_status": ARCHITECTURE_STATUS,
            "engineering_status": ENGINEERING_STATUS, "qa_status": QA_STATUS,
            "security_status": SECURITY_STATUS, "devops_status": DEVOPS_STATUS,
            "document_status": DOCUMENT_STATUS, "validation_state": VALIDATION_STATE,
            "publication_state": PUBLICATION_STATE, "pilot_status": PILOT_STATUS,
        }:
            raise ValueError("Documentation source states are invalid")
        status = _closed_object(values["status_report_json"], {
            "state", "completed_items", "next_actions", "blockers", "escalations",
        })
        document_keys = (
            "technical_document_json", "user_document_json", "api_document_json",
            "operations_document_json", "release_document_json",
        )
        documents = tuple(_document(json.loads(values[key])) for key in document_keys)
        handoff = _closed_object(values["customer_handoff_json"], {
            "handoff_id", "audience", "readiness_summary", "deliverable_document_ids",
            "review_checklist", "known_limitations", "next_actions", "publication_state",
        })
        acceptance = _string_items(values["acceptance_checks_json"])
        if acceptance != work_order.acceptance_checks:
            raise ValueError("Documentation acceptance checks changed")
        sources = tuple(
            DocumentationEngineeringSource(
                artifact_id=item.artifact_id, execution_id=item.execution_id,
                business_role=item.business_role, artifact_digest=item.digest,
                architecture_artifact_digest=item.architecture_artifact_digest,
                target_component_ids=item.target_component_ids,
                interface_contract_ids=tuple(contract.contract_id for contract in item.interface_contracts),
                status=item.status, pilot_status=item.pilot_status,
            )
            for item in engineering_artifacts
        )
        return DocumentationWorkArtifact(
            artifact_id=artifact_id_for(execution_id), work_order_id=work_order.work_order_id,
            work_order_digest=work_order.digest, tenant_id=work_order.tenant_id,
            opportunity_id=work_order.opportunity_id, execution_id=execution_id,
            assignment_id=work_order.assignment_id, twin_id=twin.twin_id,
            business_role=DOCUMENTATION_ROLE, provider_id=twin.provider_id,
            opportunity_digest=architecture.opportunity_digest,
            architecture_artifact_id=architecture.artifact_id,
            architecture_artifact_digest=architecture.digest, architecture_status=architecture.status,
            sources=sources, qa_artifact_id=qa_artifact.artifact_id,
            qa_artifact_digest=qa_artifact.digest, qa_status=qa_artifact.status,
            security_artifact_id=security_artifact.artifact_id,
            security_artifact_digest=security_artifact.digest, security_status=security_artifact.status,
            devops_artifact_id=devops_artifact.artifact_id,
            devops_artifact_digest=devops_artifact.digest, devops_status=devops_artifact.status,
            capability_ids=DOCUMENTATION_CAPABILITIES, action_ids=DOCUMENTATION_ACTIONS,
            title=values["title"], summary=values["summary"], documents=documents,
            customer_handoff=CustomerHandoff(
                handoff_id=handoff["handoff_id"], audience=_object_strings(handoff, "audience"),
                readiness_summary=handoff["readiness_summary"],
                deliverable_document_ids=_object_strings(handoff, "deliverable_document_ids"),
                review_checklist=_object_strings(handoff, "review_checklist"),
                known_limitations=_object_strings(handoff, "known_limitations"),
                next_actions=_object_strings(handoff, "next_actions"),
                publication_state=handoff["publication_state"],
            ),
            acceptance_checks=acceptance,
            coverage_requirements=_string_items(values["coverage_requirements_json"]),
            status_report=DocumentationStatusReport(
                state=status["state"], completed_items=_object_strings(status, "completed_items"),
                next_actions=_object_strings(status, "next_actions"),
                blockers=_object_strings(status, "blockers"),
                escalations=_object_strings(status, "escalations"),
            ),
            authority_digest=authority.digest, assignment_digest=assignment.digest,
            request_digest=receipt.request_digest, output_digest=receipt.output_digest,
            receipt_digest=receipt.digest, generated_at=receipt.completed_at,
        )
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
        raise DocumentationWorkforcePolicyError(
            "Documentation provider output failed typed validation"
        ) from error


def _document(value: object) -> DocumentationRecord:
    keys = {
        "document_id", "kind", "title", "audience", "purpose",
        "source_artifact_digests", "sections", "validation_checks",
        "validation_state", "publication_state", "status",
    }
    if not isinstance(value, dict) or set(value) != keys:
        raise ValueError("Documentation record is not closed")
    sections = value["sections"]
    if not isinstance(sections, list):
        raise ValueError("Documentation sections are invalid")
    return DocumentationRecord(
        document_id=value["document_id"], kind=DocumentationKind(value["kind"]),
        title=value["title"], audience=_object_strings(value, "audience"),
        purpose=value["purpose"],
        source_artifact_digests=_object_strings(value, "source_artifact_digests"),
        sections=tuple(_section(item) for item in sections),
        validation_checks=_object_strings(value, "validation_checks"),
        validation_state=value["validation_state"],
        publication_state=value["publication_state"], status=value["status"],
    )


def _section(value: object) -> DocumentationSection:
    if not isinstance(value, dict) or set(value) != {"section_id", "heading", "content"}:
        raise ValueError("Documentation section is not closed")
    return DocumentationSection(**value)


def _closed_object(value: str, keys: set[str]) -> dict:
    decoded = json.loads(value)
    if not isinstance(decoded, dict) or set(decoded) != keys:
        raise ValueError("Documentation output object is invalid")
    return decoded


def _string_items(value: str) -> tuple[str, ...]:
    decoded = json.loads(value)
    if not isinstance(decoded, list) or any(not isinstance(item, str) for item in decoded):
        raise ValueError("Documentation output collection is invalid")
    return tuple(decoded)


def _object_strings(value: dict, key: str) -> tuple[str, ...]:
    items = value[key]
    if not isinstance(items, list) or any(not isinstance(item, str) for item in items):
        raise ValueError("Documentation nested collection is invalid")
    return tuple(items)


def _json(value: object) -> str:
    return json.dumps(value, separators=(",", ":"), ensure_ascii=False)
