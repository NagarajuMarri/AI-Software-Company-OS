"""Closed providers for ASCOS V1 hardening and acceptance."""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime, timedelta, timezone

from runtime.v1_hardening_acceptance.errors import V1HardeningPolicyError
from runtime.v1_hardening_acceptance.models import (
    DOCUMENTATION_IDS,
    HARDENING_CONTROL_IDS,
    HARDENING_CONTROL_STATES,
    MONITORING_SIGNAL_IDS,
    V1_HARDENING_ACTIONS,
    V1_HARDENING_TOOL_IDS,
    HardeningControlReceipt,
    MonitoringSignalReceipt,
    V1HardeningAuthority,
    V1HardeningObservation,
    V1HardeningSourceSnapshot,
    V1HardeningWorkOrder,
    audit_digest_for,
    canonical_digest,
)


class V1HardeningProvider(ABC):
    """Provider contract limited to verified digest-only Day 37 inputs."""

    provider_id: str

    @abstractmethod
    def execute(
        self,
        work_order: V1HardeningWorkOrder,
        authority: V1HardeningAuthority,
        snapshot: V1HardeningSourceSnapshot,
    ) -> V1HardeningObservation:
        """Return terminal hardening receipts without external side effects."""


class ControlledV1HardeningProvider(V1HardeningProvider):
    """Enforce the Day 37 zero-external-effect provider boundary."""

    def __init__(self, inner: V1HardeningProvider) -> None:
        self.inner = inner
        self.provider_id = inner.provider_id
        self.execution_count = 0

    def execute(
        self,
        work_order: V1HardeningWorkOrder,
        authority: V1HardeningAuthority,
        snapshot: V1HardeningSourceSnapshot,
    ) -> V1HardeningObservation:
        if authority.allowed_action_ids != V1_HARDENING_ACTIONS:
            raise V1HardeningPolicyError("Day 37 action authority is invalid")
        if authority.allowed_tool_ids != V1_HARDENING_TOOL_IDS:
            raise V1HardeningPolicyError("Day 37 tool authority is invalid")
        if work_order.control_source_digests != snapshot.control_source_digests:
            raise V1HardeningPolicyError("Day 37 control source binding changed")
        if work_order.source_pilot_artifact_digest != snapshot.source_pilot_artifact_digest:
            raise V1HardeningPolicyError("Day 36 pilot binding changed")
        self.execution_count += 1
        observation = self.inner.execute(work_order, authority, snapshot)
        if not isinstance(observation, V1HardeningObservation):
            raise V1HardeningPolicyError("Day 37 provider returned an invalid observation")
        return observation


class OfflineV1HardeningProvider(V1HardeningProvider):
    """Deterministic provider that evaluates only the verified source snapshot."""

    provider_id = "offline-v1-hardening-acceptance-v1"

    def __init__(self, clock=None) -> None:  # noqa: ANN001
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        self.calls = 0

    def execute(
        self,
        work_order: V1HardeningWorkOrder,
        authority: V1HardeningAuthority,
        snapshot: V1HardeningSourceSnapshot,
    ) -> V1HardeningObservation:
        del work_order, authority
        self.calls += 1
        now = self.clock()
        evidence = (
            ("day27-security", "day36-zero-elevated-effects"),
            ("canonical-primary", "verified-backup-copy"),
            ("explicit-restore-drill", "exact-artifact-readback"),
            ("ordered-control-chain", "digest-integrity"),
            MONITORING_SIGNAL_IDS,
            DOCUMENTATION_IDS,
            snapshot.journey_ids,
        )
        receipts: list[HardeningControlReceipt] = []
        previous = "0" * 64
        for index, (control_id, state, source_digest, evidence_ids) in enumerate(
            zip(
                HARDENING_CONTROL_IDS,
                HARDENING_CONTROL_STATES,
                snapshot.control_source_digests,
                evidence,
                strict=True,
            )
        ):
            verified_at = now + timedelta(seconds=index)
            digest = audit_digest_for(
                control_id,
                source_digest,
                state,
                tuple(evidence_ids),
                verified_at,
                previous,
            )
            receipts.append(
                HardeningControlReceipt(
                    control_id=control_id,
                    source_digest=source_digest,
                    state=state,
                    evidence_ids=tuple(evidence_ids),
                    verified_at=verified_at,
                    previous_audit_digest=previous,
                    audit_digest=digest,
                )
            )
            previous = digest
        monitoring = tuple(
            MonitoringSignalReceipt(
                signal_id=signal_id,
                state="HEALTHY",
                evidence_digest=canonical_digest(
                    {
                        "snapshot_digest": snapshot.digest,
                        "signal_id": signal_id,
                        "state": "HEALTHY",
                    }
                ),
                observed_at=now + timedelta(seconds=20 + index),
            )
            for index, signal_id in enumerate(MONITORING_SIGNAL_IDS)
        )
        return V1HardeningObservation(
            provider_id=self.provider_id,
            pilot_id=snapshot.pilot_id,
            snapshot_digest=snapshot.digest,
            control_receipts=tuple(receipts),
            monitoring_receipts=monitoring,
            documentation_ids=DOCUMENTATION_IDS,
        )
