from dataclasses import dataclass

from runtime.operations.exceptions import (
    ForgedProviderResultError, UnsupportedPayloadVersionError,
)


@dataclass(frozen=True)
class ProviderDispatchResult:
    operation_id: str
    provider_id: str
    result_reference: str
    result_payload: dict


class DeterministicOperationHandler:
    def __init__(
        self,
        operation_type,
        *,
        payload_versions=(1,),
        required_capability="dispatch",
        provider_idempotency=True,
        timeout_seconds=30,
    ):
        self.operation_type = operation_type
        self.payload_versions = frozenset(payload_versions)
        self.required_capability = required_capability
        self.provider_idempotency = provider_idempotency
        self.timeout_seconds = timeout_seconds

    def validate(self, operation):
        if operation.payload_schema_version not in self.payload_versions:
            raise UnsupportedPayloadVersionError(
                "Unsupported operation payload schema"
            )

    def dispatch(self, provider, operation):
        from runtime.outbox.models import (
            validate_payload, validate_safe_reference,
        )
        self.validate(operation)
        result = provider.dispatch(
            operation.operation_type,
            {**dict(operation.payload), "operation_id": operation.operation_id},
            idempotency_key=operation.idempotency_key,
        )
        if (
            not isinstance(result, ProviderDispatchResult)
            or result.operation_id != operation.operation_id
            or result.provider_id != operation.provider_id
        ):
            raise ForgedProviderResultError("Provider result identity is invalid")
        validate_safe_reference(result.result_reference)
        validate_payload(result.result_payload)
        return result
