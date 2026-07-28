import pytest

from runtime.outbox.exceptions import OutboxValidationError


def test_operation_payload_is_recursive_immutable(operation_factory):
    operation = operation_factory(payload={"nested": {"items": [1, 2]}})
    with pytest.raises(TypeError):
        operation.payload["nested"]["items"] = ()
    assert operation.request_fingerprint()


def test_secret_and_oversized_payloads_are_rejected(operation_factory):
    with pytest.raises(OutboxValidationError, match="Secret"):
        operation_factory(payload={"api_token": "value"})
    with pytest.raises(OutboxValidationError, match="size"):
        operation_factory(payload={"value": "x" * 40_000})
    with pytest.raises(OutboxValidationError, match="Secret"):
        operation_factory(payload={"value": "ghp_" + "x" * 30})


def test_malicious_operation_and_provider_are_rejected(operation_factory):
    with pytest.raises(OutboxValidationError):
        operation_factory(operation_type="BAD;DROP")
    with pytest.raises(OutboxValidationError):
        operation_factory(provider_id="../provider")
