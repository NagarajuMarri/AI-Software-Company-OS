from datetime import datetime

from runtime.outbox.models import (
    FailureCategory, OutboxAttempt, OutboxOperation, OutboxStatus,
    ReconciliationState, plain,
)

_DATES = {
    "available_at", "created_at", "first_attempted_at", "last_attempted_at",
    "completed_at", "claimed_at", "claim_expires_at", "retry_after",
}


def operation_to_dict(item):
    value = dict(vars(item))
    value["payload"] = plain(item.payload)
    value["status"] = item.status.value
    value["failure_category"] = (
        item.failure_category.value if item.failure_category else None
    )
    value["reconciliation_state"] = item.reconciliation_state.value
    for key in _DATES:
        value[key] = value[key].isoformat() if value[key] else None
    return value


def operation_from_dict(value):
    copied = dict(value)
    copied["status"] = OutboxStatus(copied["status"])
    copied["failure_category"] = (
        FailureCategory(copied["failure_category"])
        if copied["failure_category"] else None
    )
    copied["reconciliation_state"] = ReconciliationState(
        copied["reconciliation_state"]
    )
    for key in _DATES:
        copied[key] = datetime.fromisoformat(copied[key]) if copied[key] else None
    return OutboxOperation(**copied)


def encode_state(state):
    return {
        "schema_version": 1,
        "operations": {
            key: operation_to_dict(item)
            for key, item in state["operations"].items()
        },
        "attempts": {
            key: [
                {
                    **dict(vars(item)),
                    "started_at": item.started_at.isoformat(),
                    "completed_at": (
                        item.completed_at.isoformat()
                        if item.completed_at else None
                    ),
                    "failure_category": (
                        item.failure_category.value
                        if item.failure_category else None
                    ),
                }
                for item in values
            ]
            for key, values in state["attempts"].items()
        },
        "idempotency": dict(state["idempotency"]),
        "provider_pauses": dict(state["provider_pauses"]),
        "audit": list(state["audit"]),
    }


def decode_state(value):
    if value.get("schema_version") != 1:
        raise ValueError("Unsupported outbox file schema")
    return {
        "operations": {
            key: operation_from_dict(item)
            for key, item in value["operations"].items()
        },
        "attempts": {
            key: [
                OutboxAttempt(
                    item["operation_id"], item["attempt_number"],
                    datetime.fromisoformat(item["started_at"]),
                    datetime.fromisoformat(item["completed_at"])
                    if item["completed_at"] else None,
                    item["outcome"], item["failure_code"],
                    FailureCategory(item["failure_category"])
                    if item["failure_category"] else None,
                    item["safe_summary"],
                )
                for item in values
            ]
            for key, values in value["attempts"].items()
        },
        "idempotency": dict(value["idempotency"]),
        "provider_pauses": dict(value["provider_pauses"]),
        "audit": list(value["audit"]),
    }
