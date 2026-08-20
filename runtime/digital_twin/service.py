"""Fail-closed orchestration for provider-neutral Digital Twin executions."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone
import hmac

from runtime.digital_twin.contracts import DigitalTwinProvider
from runtime.digital_twin.errors import (
    DigitalTwinExecutionError,
    DigitalTwinPolicyError,
    DigitalTwinRegistryError,
    DigitalTwinToolPolicyError,
)
from runtime.digital_twin.models import (
    DelegatedAuthority,
    DigitalTwinAssignment,
    DigitalTwinDefinition,
    DigitalTwinExecutionIntent,
    DigitalTwinExecutionReceipt,
    DigitalTwinExecutionStatus,
    ProviderExecutionRequest,
    ProviderExecutionResult,
    canonical_digest,
    canonical_json,
    receipt_id_for,
    validate_identifier,
)
from runtime.digital_twin.persistence import FileDigitalTwinExecutionStore
from runtime.digital_twin.registry import (
    DigitalTwinProviderRegistry,
    DigitalTwinToolRegistry,
)
from runtime.digital_twin.tools import BoundedToolGateway


class DigitalTwinRuntime:
    """Execute one exact assignment inside explicit role, tool, and authority limits."""

    def __init__(
        self,
        providers: DigitalTwinProviderRegistry,
        tools: DigitalTwinToolRegistry,
        store: FileDigitalTwinExecutionStore,
        *,
        clock: Callable[[], datetime] | None = None,
        allow_live_providers: bool = False,
    ) -> None:
        if not isinstance(providers, DigitalTwinProviderRegistry):
            raise TypeError("providers must be a DigitalTwinProviderRegistry")
        if not isinstance(tools, DigitalTwinToolRegistry):
            raise TypeError("tools must be a DigitalTwinToolRegistry")
        if not isinstance(store, FileDigitalTwinExecutionStore):
            raise TypeError("store must be a FileDigitalTwinExecutionStore")
        if not isinstance(allow_live_providers, bool):
            raise TypeError("allow_live_providers must be boolean")
        self._providers = providers
        self._tools = tools
        self._store = store
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._allow_live_providers = allow_live_providers

    def execute(
        self,
        *,
        execution_id: str,
        twin: DigitalTwinDefinition,
        assignment: DigitalTwinAssignment,
        authority: DelegatedAuthority,
    ) -> DigitalTwinExecutionReceipt:
        """Run or reopen one digest-identical execution without elevating authority."""

        try:
            validate_identifier(execution_id, "Digital Twin execution ID")
        except ValueError as error:
            raise DigitalTwinPolicyError("Digital Twin execution identity is invalid") from error
        now = self._now()
        provider = self._validate_and_select(twin, assignment, authority, now)
        request = ProviderExecutionRequest(
            execution_id,
            twin.provider_id,
            twin.twin_id,
            twin.digest,
            assignment.assignment_id,
            assignment.digest,
            authority.authority_id,
            authority.digest,
            assignment.tenant_id,
            assignment.business_role,
            assignment.objective,
            assignment.context,
            assignment.required_capability_ids,
            authority.allowed_action_ids,
            assignment.requested_tool_ids,
            authority.expires_at,
            authority.max_tool_calls,
            authority.max_output_bytes,
        )

        with self._store.execution_lock(assignment.tenant_id, execution_id):
            intent = self._store.find_intent(assignment.tenant_id, execution_id)
            existing_receipt = self._store.find_receipt(
                assignment.tenant_id,
                execution_id,
            )
            if existing_receipt is not None:
                if intent is None:
                    raise DigitalTwinExecutionError(
                        "Digital Twin receipt exists without its execution intent"
                    )
                self._validate_intent(intent, request, twin, assignment, authority)
                self._validate_receipt(
                    existing_receipt,
                    intent,
                    request,
                    twin,
                    assignment,
                    authority,
                )
                return existing_receipt

            if intent is None:
                intent = self._store.save_intent(
                    DigitalTwinExecutionIntent(
                        execution_id,
                        assignment.tenant_id,
                        twin.twin_id,
                        twin.digest,
                        assignment.assignment_id,
                        assignment.digest,
                        authority.authority_id,
                        authority.digest,
                        provider.provider_id,
                        request.digest,
                        now,
                    )
                )
            else:
                self._validate_intent(intent, request, twin, assignment, authority)
                if provider.requires_live_authorization:
                    raise DigitalTwinExecutionError(
                        "Live Digital Twin execution requires reconciliation after interruption"
                    )

            started_at = self._now()
            gateway = BoundedToolGateway(
                self._tools,
                allowed_tool_ids=assignment.requested_tool_ids,
                max_tool_calls=authority.max_tool_calls,
                max_output_bytes=authority.max_output_bytes,
                authority_expires_at=authority.expires_at,
                clock=self._now,
            )
            status = DigitalTwinExecutionStatus.FAILED
            summary = "Digital Twin provider execution failed closed"
            failure_code: str | None = "PROVIDER_EXECUTION_FAILURE"
            output_digest = canonical_digest([])
            try:
                result = provider.execute(request, gateway)
                self._validate_result(result, request, provider.provider_id, gateway)
                if self._now() >= authority.expires_at:
                    raise DigitalTwinPolicyError(
                        "Digital Twin authority expired during provider execution"
                    )
                status = result.status
                summary = (
                    "Bounded Digital Twin execution completed"
                    if result.status is DigitalTwinExecutionStatus.SUCCEEDED
                    else "Digital Twin provider reported a bounded failure"
                )
                failure_code = result.failure_code
                output_digest = result.output_digest
            except DigitalTwinToolPolicyError:
                failure_code = "TOOL_POLICY_FAILURE"
                summary = "Digital Twin tool request exceeded delegated authority"
            except DigitalTwinPolicyError:
                failure_code = "AUTHORITY_POLICY_FAILURE"
                summary = "Digital Twin provider exceeded delegated authority"
            except (DigitalTwinExecutionError, DigitalTwinRegistryError):
                failure_code = "BOUNDED_EXECUTION_FAILURE"
                summary = "Digital Twin provider execution failed closed"
            except Exception:
                failure_code = "INVALID_PROVIDER_RESULT"
                summary = "Digital Twin provider result failed validation"

            receipt = DigitalTwinExecutionReceipt(
                receipt_id_for(execution_id),
                execution_id,
                assignment.tenant_id,
                twin.twin_id,
                twin.digest,
                assignment.assignment_id,
                assignment.digest,
                authority.authority_id,
                authority.digest,
                provider.provider_id,
                request.digest,
                intent.digest,
                status,
                summary,
                output_digest,
                gateway.evidence,
                failure_code,
                started_at,
                self._now(),
            )
            return self._store.save_receipt(receipt)

    def _validate_and_select(
        self,
        twin: DigitalTwinDefinition,
        assignment: DigitalTwinAssignment,
        authority: DelegatedAuthority,
        now: datetime,
    ) -> DigitalTwinProvider:
        if not isinstance(twin, DigitalTwinDefinition) or not twin.enabled:
            raise DigitalTwinPolicyError("Digital Twin is not enabled")
        if not isinstance(assignment, DigitalTwinAssignment):
            raise DigitalTwinPolicyError("Digital Twin assignment is invalid")
        if not isinstance(authority, DelegatedAuthority):
            raise DigitalTwinPolicyError("Digital Twin authority is invalid")
        if not (
            twin.twin_id == assignment.twin_id == authority.twin_id
            and twin.business_role is assignment.business_role is authority.business_role
            and assignment.tenant_id == authority.tenant_id
            and assignment.assignment_id == authority.assignment_id
            and assignment.authority_id == authority.authority_id
            and hmac.compare_digest(assignment.authority_digest, authority.digest)
            and hmac.compare_digest(assignment.objective_digest, authority.objective_digest)
        ):
            raise DigitalTwinPolicyError(
                "Digital Twin role, assignment, or delegated authority does not match"
            )
        if not (
            authority.issued_at <= assignment.created_at <= authority.expires_at
            and authority.issued_at <= now < authority.expires_at
        ):
            raise DigitalTwinPolicyError("Digital Twin delegated authority is not current")
        if not set(assignment.required_capability_ids) <= set(twin.capability_ids):
            raise DigitalTwinPolicyError("Digital Twin lacks a required capability")
        if not set(assignment.requested_tool_ids) <= set(authority.allowed_tool_ids):
            raise DigitalTwinPolicyError("Assignment requested a tool outside delegated authority")
        if not set(assignment.requested_tool_ids) <= set(twin.approved_tool_ids):
            raise DigitalTwinPolicyError("Assignment requested an unapproved Digital Twin tool")

        provider = self._providers.get(twin.provider_id)
        if assignment.business_role not in provider.supported_roles():
            raise DigitalTwinPolicyError("Provider does not support the bounded Business Role")
        if not set(assignment.required_capability_ids) <= set(
            provider.supported_capabilities()
        ):
            raise DigitalTwinPolicyError("Provider lacks a required capability")
        if not set(assignment.requested_tool_ids) <= set(provider.supported_tool_ids()):
            raise DigitalTwinPolicyError("Provider does not support every assigned tool")
        for tool_id in assignment.requested_tool_ids:
            self._tools.get(tool_id)
        if provider.requires_live_authorization and not (
            authority.live_provider_allowed and self._allow_live_providers
        ):
            raise DigitalTwinPolicyError(
                "Live Digital Twin provider requires authority and operator enablement"
            )
        return provider

    @staticmethod
    def _validate_intent(
        intent: DigitalTwinExecutionIntent,
        request: ProviderExecutionRequest,
        twin: DigitalTwinDefinition,
        assignment: DigitalTwinAssignment,
        authority: DelegatedAuthority,
    ) -> None:
        if not (
            intent.execution_id == request.execution_id
            and intent.tenant_id == assignment.tenant_id
            and intent.twin_id == twin.twin_id
            and hmac.compare_digest(intent.twin_digest, twin.digest)
            and intent.assignment_id == assignment.assignment_id
            and hmac.compare_digest(intent.assignment_digest, assignment.digest)
            and intent.authority_id == authority.authority_id
            and hmac.compare_digest(intent.authority_digest, authority.digest)
            and intent.provider_id == request.provider_id
            and hmac.compare_digest(intent.request_digest, request.digest)
        ):
            raise DigitalTwinExecutionError(
                "Persisted Digital Twin intent does not match exact authority"
            )

    @staticmethod
    def _validate_receipt(
        receipt: DigitalTwinExecutionReceipt,
        intent: DigitalTwinExecutionIntent,
        request: ProviderExecutionRequest,
        twin: DigitalTwinDefinition,
        assignment: DigitalTwinAssignment,
        authority: DelegatedAuthority,
    ) -> None:
        if not (
            receipt.execution_id == request.execution_id
            and receipt.tenant_id == assignment.tenant_id
            and receipt.twin_id == twin.twin_id
            and hmac.compare_digest(receipt.twin_digest, twin.digest)
            and receipt.assignment_id == assignment.assignment_id
            and hmac.compare_digest(receipt.assignment_digest, assignment.digest)
            and receipt.authority_id == authority.authority_id
            and hmac.compare_digest(receipt.authority_digest, authority.digest)
            and receipt.provider_id == request.provider_id
            and hmac.compare_digest(receipt.request_digest, request.digest)
            and hmac.compare_digest(receipt.intent_digest, intent.digest)
        ):
            raise DigitalTwinExecutionError(
                "Persisted Digital Twin receipt does not match exact authority"
            )

    @staticmethod
    def _validate_result(
        result: object,
        request: ProviderExecutionRequest,
        provider_id: str,
        gateway: BoundedToolGateway,
    ) -> None:
        if not isinstance(result, ProviderExecutionResult):
            raise DigitalTwinExecutionError("Provider returned an invalid result type")
        if not (
            result.execution_id == request.execution_id
            and result.provider_id == provider_id
            and hmac.compare_digest(result.request_digest, request.digest)
        ):
            raise DigitalTwinExecutionError("Provider result identity is invalid")
        output_bytes = len(
            canonical_json(
                {
                    "summary": result.summary,
                    "output": [
                        {"key": item.key, "value": item.value} for item in result.output
                    ],
                }
            ).encode("utf-8")
        )
        if gateway.used_output_bytes + output_bytes > request.max_output_bytes:
            raise DigitalTwinExecutionError("Provider result exceeds its output budget")

    def _now(self) -> datetime:
        value = self._clock()
        if (
            not isinstance(value, datetime)
            or value.tzinfo is None
            or value.utcoffset() is None
        ):
            raise ValueError("Digital Twin runtime clock must be timezone-aware")
        return value.astimezone(timezone.utc)
