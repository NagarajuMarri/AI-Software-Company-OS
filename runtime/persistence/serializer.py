"""Safe canonical JSON-compatible serialization."""

import json
from datetime import datetime
from enum import Enum
from typing import Mapping

from runtime.agents.role import AgentRole
from runtime.agents.state import AgentState
from runtime.events.types import EventType
from runtime.execution.recovery import RecoveryAction
from runtime.execution.result import ExecutionStatus
from runtime.models.lifecycle import LifecycleState
from runtime.orchestration.assignment import AssignmentStatus
from runtime.persistence.exceptions import CheckpointCorruptedError
from runtime.workflows.models import WorkflowStage


ENUM_TYPES = {
    cls.__name__: cls
    for cls in (
        AgentRole,
        AgentState,
        EventType,
        RecoveryAction,
        ExecutionStatus,
        LifecycleState,
        AssignmentStatus,
        WorkflowStage,
    )
}


class CanonicalSerializer:
    """Encode only an explicit safe value contract."""

    @classmethod
    def encode_value(cls, value: object) -> object:
        if value is None or isinstance(value, (str, int, float, bool)):
            return value
        if isinstance(value, datetime):
            return {"$type": "datetime", "value": value.isoformat()}
        if isinstance(value, Enum):
            return {
                "$type": "enum",
                "enum": type(value).__name__,
                "value": value.value,
            }
        if isinstance(value, (bytes, bytearray)):
            return {"$type": "bytes", "value": bytes(value).hex()}
        if isinstance(value, Mapping):
            return {
                "$type": "mapping",
                "items": {
                    str(key): cls.encode_value(item)
                    for key, item in sorted(
                        value.items(),
                        key=lambda pair: str(pair[0]),
                    )
                },
            }
        if isinstance(value, (list, tuple)):
            return {
                "$type": "sequence",
                "items": [cls.encode_value(item) for item in value],
            }
        if isinstance(value, (set, frozenset)):
            encoded = [cls.encode_value(item) for item in value]
            encoded.sort(key=cls.dumps)
            return {"$type": "set", "items": encoded}
        raise TypeError(
            f"Unsupported persistence value: {type(value).__name__}"
        )

    @classmethod
    def decode_value(cls, value: object) -> object:
        if value is None or isinstance(value, (str, int, float, bool)):
            return value
        if not isinstance(value, Mapping) or "$type" not in value:
            raise CheckpointCorruptedError("Malformed typed persistence value")
        kind = value.get("$type")
        try:
            if kind == "datetime":
                parsed = datetime.fromisoformat(value["value"])
                if parsed.tzinfo is None:
                    raise ValueError
                return parsed
            if kind == "enum":
                enum_type = ENUM_TYPES[value["enum"]]
                return enum_type(value["value"])
            if kind == "bytes":
                return bytes.fromhex(value["value"])
            if kind == "mapping":
                return {
                    key: cls.decode_value(item)
                    for key, item in value["items"].items()
                }
            if kind in {"sequence", "set"}:
                decoded = [
                    cls.decode_value(item) for item in value["items"]
                ]
                return tuple(decoded) if kind == "sequence" else frozenset(decoded)
        except (KeyError, TypeError, ValueError) as error:
            raise CheckpointCorruptedError(
                "Malformed persistence value"
            ) from error
        raise CheckpointCorruptedError(
            f"Unknown persistence type discriminator {kind!r}"
        )

    @staticmethod
    def dumps(value: object) -> str:
        return json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )

    @classmethod
    def loads(cls, value: str) -> object:
        try:
            return json.loads(value)
        except (json.JSONDecodeError, TypeError) as error:
            raise CheckpointCorruptedError("Malformed JSON") from error
