"""Minimum-authority tool gateway and deterministic read-only fixture tool."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable

from runtime.digital_twin.errors import (
    DigitalTwinExecutionError,
    DigitalTwinToolPolicyError,
)
from runtime.digital_twin.models import (
    ToolCallEvidence,
    ToolCallOutcome,
    canonical_digest,
    canonical_json,
    validate_identifier,
    validate_public_field,
)
from runtime.digital_twin.registry import DigitalTwinToolRegistry


class BoundedToolGateway:
    """Enforce the exact tool allowlist and call/output budgets."""

    def __init__(
        self,
        registry: DigitalTwinToolRegistry,
        *,
        allowed_tool_ids: tuple[str, ...],
        max_tool_calls: int,
        max_output_bytes: int,
        authority_expires_at: datetime,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._registry = registry
        self._allowed = frozenset(allowed_tool_ids)
        self._max_calls = max_tool_calls
        self._max_output_bytes = max_output_bytes
        self._authority_expires_at = authority_expires_at
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._used_output_bytes = 0
        self._evidence: list[ToolCallEvidence] = []

    @property
    def evidence(self) -> tuple[ToolCallEvidence, ...]:
        return tuple(self._evidence)

    @property
    def used_output_bytes(self) -> int:
        return self._used_output_bytes

    def invoke(self, tool_id: str, values: Mapping[str, str]) -> Mapping[str, str]:
        try:
            validate_identifier(tool_id, "Digital Twin tool-call tool ID")
        except ValueError as error:
            raise DigitalTwinToolPolicyError(
                "Digital Twin requested an invalid tool"
            ) from error
        self._require_current_authority()
        if tool_id not in self._allowed:
            raise DigitalTwinToolPolicyError(
                "Digital Twin requested a tool outside its authority"
            )
        if len(self._evidence) >= self._max_calls:
            raise DigitalTwinToolPolicyError("Digital Twin tool-call budget was exhausted")
        request = _bounded_values(values, label="tool request")
        request_digest = canonical_digest(request)
        sequence = len(self._evidence) + 1
        tool = self._registry.get(tool_id)
        try:
            response = _bounded_values(tool.invoke(dict(request)), label="tool response")
            output_bytes = len(canonical_json(response).encode("utf-8"))
            if self._used_output_bytes + output_bytes > self._max_output_bytes:
                raise DigitalTwinToolPolicyError(
                    "Digital Twin tool output budget was exceeded"
                )
            self._require_current_authority()
        except DigitalTwinToolPolicyError:
            self._evidence.append(
                ToolCallEvidence(
                    sequence,
                    tool_id,
                    request_digest,
                    ToolCallOutcome.FAILED,
                    None,
                    "TOOL_POLICY_FAILURE",
                )
            )
            raise
        except Exception as error:
            self._evidence.append(
                ToolCallEvidence(
                    sequence,
                    tool_id,
                    request_digest,
                    ToolCallOutcome.FAILED,
                    None,
                    "TOOL_EXECUTION_FAILURE",
                )
            )
            raise DigitalTwinExecutionError("Assigned read-only tool failed") from error
        self._used_output_bytes += output_bytes
        self._evidence.append(
            ToolCallEvidence(
                sequence,
                tool_id,
                request_digest,
                ToolCallOutcome.SUCCEEDED,
                canonical_digest(response),
                None,
            )
        )
        return dict(response)

    def _require_current_authority(self) -> None:
        value = self._clock()
        if (
            not isinstance(value, datetime)
            or value.tzinfo is None
            or value.utcoffset() is None
            or value.astimezone(timezone.utc) >= self._authority_expires_at
        ):
            raise DigitalTwinToolPolicyError(
                "Digital Twin tool authority is invalid or expired"
            )


@dataclass(frozen=True)
class ReadOnlyRecordTool:
    """Deterministic record lookup used for safe runtime verification."""

    tool_id: str
    records: tuple[tuple[str, str], ...]
    read_only: bool = True

    def __post_init__(self) -> None:
        validate_identifier(self.tool_id, "read-only record tool ID")
        if (
            not isinstance(self.records, tuple)
            or not self.records
            or len(self.records) != len({key for key, _ in self.records})
        ):
            raise ValueError("Read-only record tool records are invalid")
        for key, value in self.records:
            validate_public_field(key, value, label="record")
        if self.read_only is not True:
            raise ValueError("Read-only record tool cannot be mutating")

    def invoke(self, values: Mapping[str, str]) -> Mapping[str, str]:
        if set(values) != {"record_key"}:
            raise ValueError("Read-only record lookup requires record_key only")
        key = values["record_key"]
        records = dict(self.records)
        if key not in records:
            raise ValueError("Read-only record was not found")
        return {"record_key": key, "record_value": records[key]}


def _bounded_values(values: object, *, label: str) -> dict[str, str]:
    if not isinstance(values, Mapping) or not 1 <= len(values) <= 16:
        raise DigitalTwinToolPolicyError(f"Digital Twin {label} is invalid")
    result: dict[str, str] = {}
    try:
        for key, value in values.items():
            validate_public_field(key, value, label=label)
            result[key] = value
    except (TypeError, ValueError) as error:
        raise DigitalTwinToolPolicyError(f"Digital Twin {label} is invalid") from error
    if len(canonical_json(result).encode("utf-8")) > 16_000:
        raise DigitalTwinToolPolicyError(
            f"Digital Twin {label} exceeds its byte limit"
        )
    return result
