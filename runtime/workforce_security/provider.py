"""Deterministic tool-free provider for the Day 27 Security Engineer agent."""

from __future__ import annotations

import json

from runtime.agents import AgentRole
from runtime.digital_twin import (
    ContextValue,
    DigitalTwinExecutionStatus,
    ProviderExecutionRequest,
    ProviderExecutionResult,
)
from runtime.digital_twin.contracts import DigitalTwinToolGateway
from runtime.workforce_engineering import ENGINEERING_ROLES
from runtime.workforce_security.models import (
    ARCHITECTURE_STATUS,
    ARTIFACT_STATUS,
    ASSIGNMENT_STATUS,
    ENGINEERING_STATUS,
    EXECUTION_STATE,
    FINDING_STATUS,
    PILOT_STATUS,
    QA_STATUS,
    SECURITY_ACTIONS,
    SECURITY_CAPABILITIES,
    SECURITY_ROLE,
    WORK_STATUS,
)


_CONTEXT_KEYS = {
    "work_order_id",
    "work_order_digest",
    "work_order_status",
    "assignment_title",
    "assignment_objective",
    "security_role",
    "opportunity_id",
    "opportunity_digest",
    "opportunity_title",
    "architecture_artifact_id",
    "architecture_artifact_digest",
    "architecture_status",
    "engineering_artifact_digests_json",
    "engineering_sources_json",
    "qa_artifact_id",
    "qa_execution_id",
    "qa_artifact_digest",
    "qa_status",
    "acceptance_checks_json",
    "security_risks_json",
    "constraints_json",
    "pilot_status",
}
_SOURCE_KEYS = {
    "artifact_digest",
    "business_role",
    "interface_contract_ids",
    "target_component_ids",
    "status",
    "pilot_status",
}


class SecurityEngineerProvider:
    """One offline provider implementing the exact zero-tool Security profile."""

    requires_live_authorization = False

    def __init__(self, provider_id: str = "deterministic-security-engineer-v1") -> None:
        if not isinstance(provider_id, str) or not provider_id:
            raise ValueError("Security provider ID is invalid")
        self.provider_id = provider_id
        self.execution_count = 0

    def supported_roles(self) -> tuple[AgentRole, ...]:
        return (SECURITY_ROLE,)

    def supported_capabilities(self) -> tuple[str, ...]:
        return SECURITY_CAPABILITIES

    def supported_tool_ids(self) -> tuple[str, ...]:
        return ()

    def execute(
        self,
        request: ProviderExecutionRequest,
        _tools: DigitalTwinToolGateway,
    ) -> ProviderExecutionResult:
        self.execution_count += 1
        return self.render(request)

    def render(self, request: ProviderExecutionRequest) -> ProviderExecutionResult:
        """Rebuild the closed Security output for retry/restart reconciliation."""

        if not isinstance(request, ProviderExecutionRequest):
            raise ValueError("Security provider request is invalid")
        if not (
            request.provider_id == self.provider_id
            and request.business_role is SECURITY_ROLE
            and request.required_capability_ids == SECURITY_CAPABILITIES
            and request.allowed_action_ids == SECURITY_ACTIONS
            and request.allowed_tool_ids == ()
            and request.max_tool_calls == 0
        ):
            raise ValueError("Security provider request profile is invalid")
        context = {item.key: item.value for item in request.context}
        if len(context) != len(request.context) or set(context) != _CONTEXT_KEYS:
            raise ValueError("Security provider context is not closed")
        if not (
            context["security_role"] == SECURITY_ROLE.value
            and context["work_order_status"] == ASSIGNMENT_STATUS
            and context["architecture_status"] == ARCHITECTURE_STATUS
            and context["qa_status"] == QA_STATUS
            and context["pilot_status"] == PILOT_STATUS
        ):
            raise ValueError("Security provider context state is invalid")
        sources = _records(context["engineering_sources_json"], _SOURCE_KEYS)
        digests = _items(context["engineering_artifact_digests_json"], "source digests")
        acceptance = _items(context["acceptance_checks_json"], "acceptance checks")
        risks = _items(context["security_risks_json"], "security risks")
        constraints = _items(context["constraints_json"], "constraints")
        if not (
            len(sources) == len(digests) == 4
            and tuple(item["business_role"] for item in sources)
            == tuple(role.value for role in ENGINEERING_ROLES)
            and tuple(item["artifact_digest"] for item in sources) == digests
            and all(item["status"] == ENGINEERING_STATUS for item in sources)
            and all(item["pilot_status"] == PILOT_STATUS for item in sources)
            and all(_string_list(item["target_component_ids"]) for item in sources)
            and all(_string_list(item["interface_contract_ids"]) for item in sources)
            and acceptance
            and risks
            and constraints
        ):
            raise ValueError("Security upstream context is incomplete")
        output = _output(
            context["assignment_title"],
            sources,
            context["qa_artifact_digest"],
            acceptance,
        )
        return ProviderExecutionResult(
            execution_id=request.execution_id,
            provider_id=self.provider_id,
            request_digest=request.digest,
            status=DigitalTwinExecutionStatus.SUCCEEDED,
            summary="Bounded Security Engineer assignment completed",
            output=tuple(ContextValue(key, value) for key, value in output),
        )


def _output(
    title: str,
    sources: tuple[dict[str, object], ...],
    qa_digest: str,
    acceptance: tuple[str, ...],
) -> tuple[tuple[str, str], ...]:
    backend, frontend, ai, data = sources
    threat_specs = (
        ("security-threat-spoofing", "SPOOFING", (backend, frontend), "Tenant identity and session",
         "External interface to authenticated service boundary",
         "A forged or cross-tenant identity could be accepted across the interface-to-service contract.",
         ("Authentication", "Tenant isolation")),
        ("security-threat-tampering", "TAMPERING", (backend, data), "Persisted product state",
         "Service-to-persistence integrity boundary",
         "Malformed or stale writes could alter source-bound state without preserving immutable digests.",
         ("Integrity", "Source binding")),
        ("security-threat-repudiation", "REPUDIATION", (backend, data), "Security-relevant decisions",
         "Request handling to immutable evidence boundary",
         "A sensitive action could lack digest-bound actor, request, outcome, and timestamp evidence.",
         ("Accountability", "Non-repudiation")),
        ("security-threat-disclosure", "INFORMATION_DISCLOSURE", (ai, data), "Tenant and provider data",
         "Data storage to bounded AI context boundary",
         "Secrets, customer content, or cross-tenant values could enter prompts, logs, or persisted output.",
         ("Confidentiality", "Data minimization")),
        ("security-threat-denial", "DENIAL_OF_SERVICE", (backend, ai), "Bounded service capacity",
         "External request to service and provider budget boundary",
         "Unbounded requests, retries, or provider output could exhaust service capacity.",
         ("Availability", "Bounded execution")),
        ("security-threat-elevation", "ELEVATION_OF_PRIVILEGE", (backend, frontend), "Delegated authority",
         "Customer control plane to privileged action boundary",
         "Client-supplied role or authority data could enable an action outside the immutable grant.",
         ("Authorization", "Least privilege")),
    )
    threats = tuple(
        {
            "threat_id": threat_id,
            "category": category,
            "source_engineering_artifact_digests": tuple(
                str(item["artifact_digest"]) for item in selected
            ),
            "target_component_ids": tuple(
                dict.fromkeys(
                    str(_string_list(item["target_component_ids"])[0])
                    for item in selected
                )
            ),
            "asset": asset,
            "trust_boundary": boundary,
            "scenario": scenario,
            "security_properties": properties,
            "mitigations": (
                "Enforce tenant, role, authority, and exact source-digest checks server-side",
                "Reject unknown fields, stale state, and values outside closed typed schemas",
                "Record sanitized digest-bound evidence without credentials or raw provider values",
            ),
            "residual_risk": (
                "Control effectiveness remains unverified until an isolated workspace permits authorized scanning and runtime validation."
            ),
            "validation_state": EXECUTION_STATE,
        }
        for threat_id, category, selected, asset, boundary, scenario, properties in threat_specs
    )
    kinds = (
        "MANIFEST_AUDIT",
        "CLIENT_SUPPLY_CHAIN",
        "AI_MODEL_PROVENANCE",
        "DATA_MIGRATION_SUPPLY_CHAIN",
    )
    dependencies = tuple(
        {
            "check_id": f"security-dependency-{str(source['business_role']).casefold().replace('_', '-')}",
            "kind": kinds[index],
            "source_engineering_artifact_digest": str(source["artifact_digest"]),
            "target_component_ids": _string_list(source["target_component_ids"]),
            "manifest_scope": (
                f"Declared direct, transitive, build, runtime, and generated dependencies for the bounded {source['business_role']} output"
            ),
            "required_checks": (
                "Resolve immutable versions and provenance against the authorized workspace lock state",
                "Identify known vulnerabilities, unsupported versions, license conflicts, and integrity drift",
                "Fail closed when manifests, lock data, checksums, or provenance are missing or inconsistent",
            ),
            "failure_threshold": "HIGH",
            "expected_evidence": (
                "Tool identity, ruleset version, manifest digests, and timestamp",
                "Sanitized findings with package identity, severity, advisory reference, and disposition",
            ),
            "execution_state": EXECUTION_STATE,
        }
        for index, source in enumerate(sources)
    )
    secrets = tuple(
        {
            "check_id": f"security-secret-{str(source['business_role']).casefold().replace('_', '-')}",
            "source_engineering_artifact_digest": str(source["artifact_digest"]),
            "target_component_ids": _string_list(source["target_component_ids"]),
            "search_scopes": (
                "Authorized workspace tracked content and approved generated artifacts",
                "Configuration, test fixtures, build output metadata, and commit-diff boundary",
            ),
            "detector_classes": (
                "Private keys and signing material",
                "Cloud, database, provider, token, cookie, and webhook credentials",
                "High-entropy values with verified context",
            ),
            "allowlist_policy": (
                "Only explicit reviewed fingerprints and synthetic test markers may be allowlisted; raw secret values are never recorded."
            ),
            "incident_response": (
                "Stop the later authorized run, redact evidence, revoke or rotate the credential, identify exposure scope, and require human review."
            ),
            "expected_evidence": (
                "Scanner and ruleset identity with source and scope digests",
                "Redacted finding fingerprints, locations, severity, and disposition only",
            ),
            "execution_state": EXECUTION_STATE,
        }
        for source in sources
    )
    findings = (
        _finding(
            "security-finding-client-authority",
            "THREAT_GAP",
            "HIGH",
            (backend, frontend),
            qa_digest,
            "Client-to-service authority enforcement requires runtime proof",
            "Engineering contracts describe a client/service boundary and QA identifies cross-tenant failure coverage, but no product workspace exists.",
            "A client-controlled identity or role could be trusted beyond its delegated server-side authority.",
            "Require negative authorization, tenant-isolation, stale-grant, and unknown-field tests before quality or security approval.",
        ),
        _finding(
            "security-finding-dependency-provenance",
            "DEPENDENCY_RISK",
            "HIGH",
            (ai, data),
            qa_digest,
            "Dependency and provenance state is not yet inspectable",
            "Engineering outputs define AI and data components while Day 27 has no authorized manifests, lockfiles, model inventory, or SBOM.",
            "Unknown or vulnerable dependencies and unverified model provenance could enter the implementation.",
            "Run the bound dependency checks in the later isolated workspace and require reviewed evidence for all high-or-greater results.",
        ),
        _finding(
            "security-finding-secret-scan",
            "SECRET_EXPOSURE_RISK",
            "CRITICAL",
            (backend, frontend, ai, data),
            qa_digest,
            "Secret scanning has not executed",
            "The exact Engineering and QA artifacts are plans only; Day 27 intentionally has no repository or credential access.",
            "A future implementation could contain credentials or sensitive tokens without detection.",
            "Run redacting secret scans on the authorized workspace and commit diff before any controlled GitHub delivery.",
        ),
    )
    return (
        ("title", f"SECURITY_ENGINEER bounded execution: {title}"),
        (
            "summary",
            "The exact architecture, four Engineering artifacts, and QA artifact were translated into a closed STRIDE threat model, dependency-check specifications, secret-check specifications, and draft findings; no scan or remediation ran.",
        ),
        ("threat_spoofing_json", _json((threats[0],))),
        ("threat_tampering_json", _json((threats[1],))),
        ("threat_repudiation_json", _json((threats[2],))),
        ("threat_disclosure_json", _json((threats[3],))),
        ("threat_denial_json", _json((threats[4],))),
        ("threat_elevation_json", _json((threats[5],))),
        ("dependency_backend_json", _json((dependencies[0],))),
        ("dependency_frontend_json", _json((dependencies[1],))),
        ("dependency_ai_json", _json((dependencies[2],))),
        ("dependency_data_json", _json((dependencies[3],))),
        ("exposure_check_backend_json", _json((secrets[0],))),
        ("exposure_check_frontend_json", _json((secrets[1],))),
        ("exposure_check_ai_json", _json((secrets[2],))),
        ("exposure_check_data_json", _json((secrets[3],))),
        ("finding_authority_json", _json((findings[0],))),
        ("finding_dependency_json", _json((findings[1],))),
        ("finding_exposure_json", _json((findings[2],))),
        (
            "coverage_requirements_json",
            _json(
                (
                    "Cover every STRIDE category and exact source digest",
                    "Cover every Engineering role with dependency and secret check specifications",
                    "Bind every finding to the exact QA artifact and relevant Engineering sources",
                    "Require redacted reproducible evidence when later execution is authorized",
                )
            ),
        ),
        (
            "handoff_notes_json",
            _json(
                (
                    "Preserve architecture, Engineering, QA, work-order, authority, request, output, and receipt digests",
                    "Scanning, remediation, workspace access, and product validation require later authorization",
                    "DevOps, Documentation, orchestration, GitHub delivery, deployment, release, and approval remain excluded",
                )
            ),
        ),
        (
            "status_report_json",
            _json(
                {
                    "state": WORK_STATUS,
                    "completed_items": ("Threat model, check specifications, and draft findings prepared",),
                    "next_actions": ("Execute approved scans only after an isolated workspace is authorized",),
                    "blockers": ("Human architecture review and an authorized product workspace remain pending",),
                    "escalations": ("Escalate critical findings, exceptions, remediation, risk acceptance, and release decisions",),
                }
            ),
        ),
        (
            "source_states_json",
            _json(
                {
                    "artifact_status": ARTIFACT_STATUS,
                    "architecture_status": ARCHITECTURE_STATUS,
                    "engineering_status": ENGINEERING_STATUS,
                    "qa_status": QA_STATUS,
                    "finding_status": FINDING_STATUS,
                    "pilot_status": PILOT_STATUS,
                }
            ),
        ),
        ("acceptance_checks_json", _json(acceptance)),
    )


def _finding(
    finding_id: str,
    kind: str,
    severity: str,
    sources: tuple[dict[str, object], ...],
    qa_digest: str,
    title: str,
    evidence_basis: str,
    risk: str,
    recommendation: str,
) -> dict[str, object]:
    return {
        "finding_id": finding_id,
        "kind": kind,
        "severity": severity,
        "source_engineering_artifact_digests": tuple(
            str(item["artifact_digest"]) for item in sources
        ),
        "qa_artifact_digest": qa_digest,
        "title": title,
        "evidence_basis": evidence_basis,
        "risk": risk,
        "recommendation": recommendation,
        "verification_requirements": (
            "Execute only in the authorized isolated workspace with exact source binding",
            "Capture sanitized deterministic evidence and require human disposition",
        ),
        "status": FINDING_STATUS,
    }


def _records(value: str, keys: set[str]) -> tuple[dict[str, object], ...]:
    decoded = json.loads(value)
    if (
        not isinstance(decoded, list)
        or any(not isinstance(item, dict) or set(item) != keys for item in decoded)
    ):
        raise ValueError("Security source records are invalid")
    return tuple(decoded)


def _items(value: str, label: str) -> tuple[str, ...]:
    decoded = json.loads(value)
    if (
        not isinstance(decoded, list)
        or not decoded
        or any(not isinstance(item, str) or not item for item in decoded)
    ):
        raise ValueError(f"Security {label} are invalid")
    return tuple(decoded)


def _string_list(value: object) -> tuple[str, ...]:
    if (
        not isinstance(value, list)
        or not value
        or any(not isinstance(item, str) or not item for item in value)
    ):
        raise ValueError("Security source collection is invalid")
    return tuple(value)


def _json(value: object) -> str:
    return json.dumps(value, separators=(",", ":"), ensure_ascii=False)
