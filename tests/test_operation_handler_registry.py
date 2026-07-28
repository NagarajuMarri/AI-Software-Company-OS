import pytest

from runtime.operations import DeterministicOperationHandler, OperationHandlerRegistry
from runtime.operations.exceptions import (
    DuplicateOperationHandlerError, UnknownOperationHandlerError,
    UnsupportedPayloadVersionError,
)


def test_handler_registry_is_deterministic():
    registry = OperationHandlerRegistry()
    registry.register(DeterministicOperationHandler("UPDATE_PULL_REQUEST"))
    registry.register(DeterministicOperationHandler("CREATE_GIT_BRANCH"))
    assert [item.operation_type for item in registry.list()] == [
        "CREATE_GIT_BRANCH", "UPDATE_PULL_REQUEST"
    ]


def test_duplicate_and_unknown_handlers_rejected():
    registry = OperationHandlerRegistry()
    handler = DeterministicOperationHandler("CREATE_GIT_BRANCH")
    registry.register(handler)
    with pytest.raises(DuplicateOperationHandlerError):
        registry.register(handler)
    with pytest.raises(UnknownOperationHandlerError):
        registry.get("MISSING_HANDLER")


def test_unsupported_payload_version_rejected(operation_factory):
    handler = DeterministicOperationHandler(
        "CREATE_GIT_BRANCH", payload_versions=(1,)
    )
    with pytest.raises(UnsupportedPayloadVersionError):
        handler.validate(operation_factory(payload_schema_version=2))


def test_default_handler_allowlist_has_no_merge_operation():
    from runtime.operations.registry import default_handler_registry
    names = {item.operation_type for item in default_handler_registry().list()}
    assert "CREATE_DRAFT_PULL_REQUEST" in names
    assert "MERGE_PULL_REQUEST" not in names
