from __future__ import annotations

from dataclasses import asdict, replace
from datetime import timedelta
import hashlib
import json
import os
from pathlib import Path

import pytest

from runtime.digital_twin import (
    ContextValue,
    DelegatedAuthority,
    DigitalTwinDefinition,
    DigitalTwinProviderRegistry,
    DigitalTwinRuntime,
    DigitalTwinToolRegistry,
    FileDigitalTwinExecutionStore,
    ProviderExecutionResult,
    USE_ASSIGNED_TOOL,
)
from runtime.workforce_architecture import FileArchitectureArtifactStore
from runtime.workforce_devops import FileDevOpsArtifactStore
from runtime.workforce_engineering import FileEngineeringArtifactStore
from runtime.workforce_qa import FileQAArtifactStore
from runtime.workforce_security import FileSecurityArtifactStore
from runtime.workforce_documentation import (
    ARTIFACT_STATUS,
    DOCUMENTATION_ACTIONS,
    DOCUMENTATION_CAPABILITIES,
    DOCUMENTATION_ROLE,
    DOCUMENT_STATUS,
    PILOT_STATUS,
    PUBLICATION_STATE,
    VALIDATION_STATE,
    WORK_STATUS,
    DocumentationEngineerProvider,
    DocumentationKind,
    DocumentationWorkOrder,
    DocumentationWorkforceCorrupt,
    DocumentationWorkforcePolicyError,
    DocumentationWorkforceService,
    FileDocumentationArtifactStore,
    documentation_objective,
)
from tests.test_workforce_devops import _run_devops
from tests.test_workforce_leadership import NOW


def _documentation_twin(**changes) -> DigitalTwinDefinition:
    values = {
        "twin_id": "twin-documentation-engineer-1",
        "display_name": "Bounded Documentation Engineer",
        "business_role": DOCUMENTATION_ROLE,
        "provider_id": "deterministic-documentation-engineer-v1",
        "capability_ids": DOCUMENTATION_CAPABILITIES,
        "approved_tool_ids": (),
    }
    values.update(changes)
    return DigitalTwinDefinition(**values)


def _documentation_work_order(architecture, sources, qa, security, devops, **changes):
    values = {
        "work_order_id": "work-order-documentation-engineer-1",
        "tenant_id": architecture.tenant_id,
        "opportunity_id": architecture.opportunity_id,
        "assignment_id": "assignment-documentation-engineer-1",
        "business_role": DOCUMENTATION_ROLE,
        "title": "Generic exact-source Documentation assignment",
        "objective": "Draft and validate technical, user, API, operations, release, and handoff documentation",
        "architecture_artifact_digest": architecture.digest,
        "engineering_artifact_digests": tuple(item.digest for item in sources),
        "qa_artifact_digest": qa.digest,
        "security_artifact_digest": security.digest,
        "devops_artifact_digest": devops.digest,
        "acceptance_checks": (
            "Exactly five document kinds bind only the persisted Architecture, Engineering, QA, Security, and DevOps sources",
            "Technical, user, API, operations, release, and customer-handoff coverage is complete",
            "Every document remains source-validated, draft, and NOT_PUBLISHED",
            "No implementation, execution, release, delivery, publication, or pilot claim is made",
        ),
        "documentation_risks": (
            "Stale source identities or unsupported prose could make documentation misleading",
            "Publication without human review could expose incomplete or sensitive information",
        ),
        "constraints": (
            "No filesystem, repository, command, network, customer channel, credential, or live provider access",
            "No document publication, product execution, deployment, release, customer delivery, or pilot selection",
        ),
        "issued_at": NOW + timedelta(minutes=40),
    }
    values.update(changes)
    return DocumentationWorkOrder(**values)


def _documentation_authority(order, architecture, sources, qa, security, devops, **changes):
    values = {
        "authority_id": "authority-documentation-engineer-1",
        "issuer_id": "founder-module-approval",
        "tenant_id": order.tenant_id,
        "assignment_id": order.assignment_id,
        "twin_id": "twin-documentation-engineer-1",
        "business_role": DOCUMENTATION_ROLE,
        "objective_digest": hashlib.sha256(
            documentation_objective(order, architecture, sources, qa, security, devops).encode()
        ).hexdigest(),
        "allowed_action_ids": DOCUMENTATION_ACTIONS,
        "allowed_tool_ids": (),
        "issued_at": NOW,
        "expires_at": NOW + timedelta(hours=4),
        "max_tool_calls": 0,
        "max_output_bytes": 128_000,
        "live_provider_allowed": False,
    }
    values.update(changes)
    return DelegatedAuthority(**values)


def _documentation_service(tmp_path: Path, *, provider=None):
    selected = provider or DocumentationEngineerProvider()
    runtime = DigitalTwinRuntime(
        DigitalTwinProviderRegistry((selected,)), DigitalTwinToolRegistry(()),
        FileDigitalTwinExecutionStore(tmp_path / "documentation-digital-twin-state"),
        clock=lambda: NOW + timedelta(minutes=43),
    )
    service = DocumentationWorkforceService(
        runtime, selected,
        FileArchitectureArtifactStore(tmp_path / "architecture-state"),
        FileEngineeringArtifactStore(tmp_path / "engineering-state"),
        FileQAArtifactStore(tmp_path / "qa-state"),
        FileSecurityArtifactStore(tmp_path / "security-state"),
        FileDevOpsArtifactStore(tmp_path / "devops-state"),
        FileDocumentationArtifactStore(tmp_path / "documentation-state"),
        clock=lambda: NOW + timedelta(minutes=42),
    )
    return service, selected


def _run_documentation(tmp_path: Path):
    devops_run = _run_devops(tmp_path)
    _, _, intake, architecture, sources, qa, security, _, _, _, devops = devops_run
    order = _documentation_work_order(architecture, sources, qa, security, devops)
    twin = _documentation_twin()
    authority = _documentation_authority(order, architecture, sources, qa, security, devops)
    service, provider = _documentation_service(tmp_path)
    artifact = service.run(
        execution_id="execution-documentation-engineer-1", twin=twin, authority=authority,
        work_order=order, architecture=architecture, engineering_artifacts=sources,
        qa_artifact=qa, security_artifact=security, devops_artifact=devops,
    )
    return (
        service, provider, intake, architecture, sources, qa, security, devops,
        order, twin, authority, artifact,
    )


def _documentation_sources(tmp_path: Path):
    run = _run_devops(tmp_path)
    return run[3], run[4], run[5], run[6], run[10]


def test_documentation_engineer_produces_five_source_validated_drafts(tmp_path: Path) -> None:
    service, provider, intake, architecture, sources, qa, security, devops, order, twin, authority, artifact = _run_documentation(tmp_path)
    assert provider.execution_count == 1
    assert artifact.tenant_id == intake.tenant_id
    assert artifact.business_role is DOCUMENTATION_ROLE
    assert artifact.work_order_digest == order.digest
    assert artifact.architecture_artifact_digest == architecture.digest
    assert tuple(item.artifact_digest for item in artifact.sources) == tuple(item.digest for item in sources)
    assert (artifact.qa_artifact_digest, artifact.security_artifact_digest, artifact.devops_artifact_digest) == (qa.digest, security.digest, devops.digest)
    assert tuple(item.kind for item in artifact.documents) == tuple(DocumentationKind)
    assert all(item.validation_state == VALIDATION_STATE for item in artifact.documents)
    assert all(item.publication_state == PUBLICATION_STATE for item in artifact.documents)
    assert all(item.status == DOCUMENT_STATUS for item in artifact.documents)
    assert artifact.customer_handoff.deliverable_document_ids == tuple(item.document_id for item in artifact.documents)
    assert artifact.customer_handoff.publication_state == PUBLICATION_STATE
    assert artifact.capability_ids == twin.capability_ids == DOCUMENTATION_CAPABILITIES
    assert artifact.action_ids == authority.allowed_action_ids == DOCUMENTATION_ACTIONS
    assert artifact.status_report.state == WORK_STATUS
    assert artifact.status == ARTIFACT_STATUS and artifact.pilot_status == PILOT_STATUS
    assert service.get(artifact.tenant_id, artifact.execution_id) == artifact


def test_documentation_profile_has_zero_tools_and_no_publication_authority(tmp_path: Path) -> None:
    *_, twin, authority, artifact = _run_documentation(tmp_path)[-3:]
    assert twin.approved_tool_ids == authority.allowed_tool_ids == ()
    assert authority.max_tool_calls == 0 and authority.live_provider_allowed is False
    for forbidden in (
        USE_ASSIGNED_TOOL, "READ_PRODUCT_WORKSPACE", "WRITE_DOCUMENTATION",
        "PUBLISH_DOCUMENTATION", "SEND_CUSTOMER_HANDOFF", "WRITE_PRODUCT_REPOSITORY",
        "RUN_COMMAND", "COMMIT", "MERGE", "DEPLOY", "RELEASE", "SELECT_PILOT_PRODUCT",
        "ORCHESTRATE_MULTI_AGENT_WORKFLOW",
    ):
        assert forbidden not in artifact.action_ids


def test_exact_retry_and_restart_do_not_repeat_documentation_provider_effect(tmp_path: Path) -> None:
    service, provider, _, architecture, sources, qa, security, devops, order, twin, authority, expected = _run_documentation(tmp_path)
    kwargs = dict(
        execution_id=expected.execution_id, twin=twin, authority=authority, work_order=order,
        architecture=architecture, engineering_artifacts=sources, qa_artifact=qa,
        security_artifact=security, devops_artifact=devops,
    )
    again = service.run(**kwargs)
    restarted, restarted_provider = _documentation_service(tmp_path)
    reopened = restarted.run(**kwargs)
    assert again == reopened == expected
    assert provider.execution_count == 1 and restarted_provider.execution_count == 0


@pytest.mark.parametrize(
    "twin_change,authority_change",
    [
        ({"capability_ids": DOCUMENTATION_CAPABILITIES[:-1]}, {}),
        ({"capability_ids": tuple(reversed(DOCUMENTATION_CAPABILITIES))}, {}),
        ({"approved_tool_ids": ("filesystem",)}, {}),
        ({}, {"allowed_action_ids": DOCUMENTATION_ACTIONS[:-1]}),
        ({}, {"allowed_action_ids": tuple(reversed(DOCUMENTATION_ACTIONS))}),
        ({}, {"allowed_action_ids": DOCUMENTATION_ACTIONS + (USE_ASSIGNED_TOOL,), "allowed_tool_ids": ("filesystem",), "max_tool_calls": 1}),
        ({}, {"live_provider_allowed": True}),
    ],
)
def test_documentation_profile_drift_fails_before_provider_effect(
    tmp_path: Path, twin_change, authority_change,
) -> None:
    architecture, sources, qa, security, devops = _documentation_sources(tmp_path)
    order = _documentation_work_order(architecture, sources, qa, security, devops)
    twin = _documentation_twin(**twin_change)
    authority = _documentation_authority(
        order, architecture, sources, qa, security, devops, **authority_change
    )
    service, provider = _documentation_service(tmp_path)
    with pytest.raises(DocumentationWorkforcePolicyError):
        service.run(
            execution_id="execution-documentation-drift", twin=twin, authority=authority,
            work_order=order, architecture=architecture, engineering_artifacts=sources,
            qa_artifact=qa, security_artifact=security, devops_artifact=devops,
        )
    assert provider.execution_count == 0


def test_documentation_rejects_reordered_or_changed_sources_before_provider_effect(tmp_path: Path) -> None:
    architecture, sources, qa, security, devops = _documentation_sources(tmp_path)
    order = _documentation_work_order(architecture, sources, qa, security, devops)
    twin = _documentation_twin()
    authority = _documentation_authority(order, architecture, sources, qa, security, devops)
    service, provider = _documentation_service(tmp_path)
    for changed_sources, changed_devops in (
        (tuple(reversed(sources)), devops),
        (sources, replace(devops, summary=devops.summary + " altered")),
    ):
        with pytest.raises(DocumentationWorkforcePolicyError):
            service.run(
                execution_id="execution-documentation-source-drift", twin=twin,
                authority=authority, work_order=order, architecture=architecture,
                engineering_artifacts=changed_sources, qa_artifact=qa,
                security_artifact=security, devops_artifact=changed_devops,
            )
    assert provider.execution_count == 0


class _ExtraOutputProvider(DocumentationEngineerProvider):
    def render(self, request):
        result = super().render(request)
        return ProviderExecutionResult(
            execution_id=result.execution_id, provider_id=result.provider_id,
            request_digest=result.request_digest, status=result.status, summary=result.summary,
            output=result.output + (ContextValue("published_url", "https://example.invalid"),),
        )


def test_documentation_rejects_unknown_provider_output_field(tmp_path: Path) -> None:
    architecture, sources, qa, security, devops = _documentation_sources(tmp_path)
    order = _documentation_work_order(architecture, sources, qa, security, devops)
    twin = _documentation_twin()
    authority = _documentation_authority(order, architecture, sources, qa, security, devops)
    service, provider = _documentation_service(tmp_path, provider=_ExtraOutputProvider())
    with pytest.raises(DocumentationWorkforcePolicyError, match="not closed"):
        service.run(
            execution_id="execution-documentation-extra", twin=twin, authority=authority,
            work_order=order, architecture=architecture, engineering_artifacts=sources,
            qa_artifact=qa, security_artifact=security, devops_artifact=devops,
        )
    assert provider.execution_count == 1


def test_documentation_models_reject_publication_validation_and_pilot_claims(tmp_path: Path) -> None:
    *_, artifact = _run_documentation(tmp_path)
    with pytest.raises(ValueError, match="publication"):
        replace(artifact.documents[0], publication_state="PUBLISHED")
    with pytest.raises(ValueError, match="validation"):
        replace(artifact.documents[0], validation_state="UNVERIFIED")
    with pytest.raises(ValueError, match="pilot"):
        replace(artifact, pilot_status="SELECTED")


def test_each_document_uses_only_exact_upstream_digests(tmp_path: Path) -> None:
    *_, artifact = _run_documentation(tmp_path)
    allowed = {
        artifact.architecture_artifact_digest, artifact.qa_artifact_digest,
        artifact.security_artifact_digest, artifact.devops_artifact_digest,
        *(item.artifact_digest for item in artifact.sources),
    }
    assert all(set(item.source_artifact_digests) <= allowed for item in artifact.documents)
    assert len({item.document_id for item in artifact.documents}) == 5


def test_documentation_store_rejects_tamper_permissions_and_unknown_entry(tmp_path: Path) -> None:
    *_, artifact = _run_documentation(tmp_path)
    store = FileDocumentationArtifactStore(tmp_path / "documentation-state")
    path = tmp_path / "documentation-state" / artifact.tenant_id / artifact.execution_id / "documentation-work-v1.json"
    original = path.read_bytes()
    path.chmod(0o644)
    with pytest.raises(DocumentationWorkforceCorrupt):
        store.load(artifact.tenant_id, artifact.execution_id)
    path.chmod(0o600)
    payload = json.loads(original)
    payload["record"]["summary"] += " tampered"
    path.write_text(json.dumps(payload, sort_keys=True, separators=(",", ":")), encoding="utf-8")
    path.chmod(0o600)
    with pytest.raises(DocumentationWorkforceCorrupt):
        store.load(artifact.tenant_id, artifact.execution_id)
    path.write_bytes(original)
    path.chmod(0o600)
    (path.parent / "unknown.txt").write_text("unexpected", encoding="utf-8")
    with pytest.raises(DocumentationWorkforceCorrupt):
        store.load(artifact.tenant_id, artifact.execution_id)


def test_documentation_schema_excludes_secrets_paths_and_publication_receipts(tmp_path: Path) -> None:
    *_, artifact = _run_documentation(tmp_path)
    payload = json.dumps(asdict(artifact), default=str).casefold()
    for forbidden in (
        "credential_value", "secret_value", "access_token", "private_key",
        "connection_string", "workspace_path", "repository_url", "commit_sha",
        "publication_url", "customer_email", "deployment_url", "release_id",
    ):
        assert forbidden not in payload
    assert PUBLICATION_STATE.casefold() in payload
    assert os.stat(
        tmp_path / "documentation-state" / artifact.tenant_id / artifact.execution_id
        / "documentation-work-v1.json"
    ).st_mode & 0o777 == 0o600
