"""Feature and capability acceptance gate service."""

from dataclasses import replace
from datetime import datetime

from runtime.runtime_acceptance.lifecycle import transition
from runtime.runtime_acceptance.models import (
    AcceptanceStage,
    EvidenceArtifact,
    EvidenceKind,
    EvidenceOutcome,
    HumanAcceptance,
    JourneyResult,
    RuntimeAcceptanceRun,
    evidence_digest,
)
from runtime.runtime_acceptance.persistence import RuntimeAcceptanceStore
from runtime.runtime_acceptance.validation import validate_completeness


class RuntimeAcceptanceError(ValueError):
    """Raised when runtime acceptance policy or ordering is violated."""


class RuntimeAcceptanceService:
    def __init__(self, store: RuntimeAcceptanceStore, event_publisher=None) -> None:
        self.store = store
        self.event_publisher = event_publisher

    def plan(self, run: RuntimeAcceptanceRun) -> RuntimeAcceptanceRun:
        if run.stage is not AcceptanceStage.PLANNED:
            raise RuntimeAcceptanceError("New runtime acceptance runs start PLANNED")
        if self.store.find(run.run_id) is not None:
            raise RuntimeAcceptanceError("Runtime acceptance run already exists")
        structural = validate_completeness(run)
        structural_blockers = tuple(
            item
            for item in structural.blockers
            if item.startswith(("JOURNEY_UNKNOWN_", "MISSING_REQUIRED_", "JOURNEY_CAPABILITY_"))
        )
        if structural_blockers:
            raise RuntimeAcceptanceError(
                "Acceptance contract is incomplete: " + ", ".join(structural_blockers)
            )
        self.store.save(run)
        self._event("RUNTIME_ACCEPTANCE_PLANNED", run)
        return run

    def mark_implemented(self, product_id: str, run_id: str, now: datetime) -> RuntimeAcceptanceRun:
        return self._advance(product_id, run_id, AcceptanceStage.IMPLEMENTED, now)

    def record_automated_verification(
        self,
        product_id: str,
        run_id: str,
        evidence: tuple[EvidenceArtifact, ...],
        now: datetime,
    ) -> RuntimeAcceptanceRun:
        run = self._load(product_id, run_id)
        if run.stage is not AcceptanceStage.IMPLEMENTED:
            raise RuntimeAcceptanceError("Implementation is required before automated verification")
        self._validate_evidence(run, evidence)
        kinds = {item.kind for item in evidence}
        if not {EvidenceKind.CODE, EvidenceKind.AUTOMATED_TEST} <= kinds:
            raise RuntimeAcceptanceError("Code and automated test evidence are required")
        if any(item.outcome is not EvidenceOutcome.PASS for item in evidence):
            raise RuntimeAcceptanceError("Failed automated verification blocks advancement")
        value = replace(run, evidence=run.evidence + evidence)
        value = transition(value, AcceptanceStage.AUTOMATED_VERIFIED, now)
        return self._save(value, "AUTOMATED_VERIFICATION_PASSED")

    def record_runtime_verification(
        self,
        product_id: str,
        run_id: str,
        evidence: tuple[EvidenceArtifact, ...],
        results: tuple[JourneyResult, ...],
        now: datetime,
    ) -> RuntimeAcceptanceRun:
        run = self._load(product_id, run_id)
        if run.stage is not AcceptanceStage.AUTOMATED_VERIFIED:
            raise RuntimeAcceptanceError("Automated verification is required before runtime verification")
        self._validate_evidence(run, evidence)
        if any(item.outcome is not EvidenceOutcome.PASS for item in evidence + tuple(results)):
            raise RuntimeAcceptanceError("Failed runtime journey blocks advancement")
        if set(item.journey_id for item in results) & set(
            item.journey_id for item in run.journey_results
        ):
            raise RuntimeAcceptanceError("Journey results cannot be overwritten")
        value = replace(
            run,
            evidence=run.evidence + evidence,
            journey_results=run.journey_results + results,
        )
        report = validate_completeness(value)
        if not report.complete:
            value = replace(value, blockers=report.blockers)
            self.store.save(value)
            raise RuntimeAcceptanceError(
                "Runtime capability completeness failed: " + ", ".join(report.blockers)
            )
        value = replace(value, blockers=(), evidence_digest=report.evidence_digest)
        value = transition(value, AcceptanceStage.RUNTIME_VERIFIED, now)
        return self._save(value, "RUNTIME_VERIFICATION_PASSED")

    def request_human_acceptance(
        self, product_id: str, run_id: str, now: datetime
    ) -> RuntimeAcceptanceRun:
        run = self._load(product_id, run_id)
        if not any(item.human_acceptance_required for item in run.capabilities if item.locked):
            raise RuntimeAcceptanceError("No locked capability requires human acceptance")
        return self._advance(
            product_id, run_id, AcceptanceStage.HUMAN_ACCEPTANCE_REQUIRED, now
        )

    def record_human_acceptance(
        self,
        product_id: str,
        run_id: str,
        acceptance: HumanAcceptance,
    ) -> RuntimeAcceptanceRun:
        run = self._load(product_id, run_id)
        if run.stage is not AcceptanceStage.HUMAN_ACCEPTANCE_REQUIRED:
            raise RuntimeAcceptanceError("Run is not waiting for human acceptance")
        required = {
            item.capability_id
            for item in run.capabilities
            if item.locked and item.human_acceptance_required
        }
        if acceptance.capability_id not in required:
            raise RuntimeAcceptanceError("Capability does not require human acceptance")
        if any(
            item.capability_id == acceptance.capability_id
            for item in run.human_acceptances
        ):
            raise RuntimeAcceptanceError("Human acceptance decision already exists")
        if acceptance.commit_sha != run.commit_sha:
            raise RuntimeAcceptanceError("Human acceptance is stale for the current commit")
        if acceptance.evidence_digest != evidence_digest(run):
            raise RuntimeAcceptanceError("Human acceptance evidence is stale")
        value = replace(run, human_acceptances=run.human_acceptances + (acceptance,))
        return self._save(value, "HUMAN_ACCEPTANCE_RECORDED")

    def accept(self, product_id: str, run_id: str, now: datetime) -> RuntimeAcceptanceRun:
        run = self._load(product_id, run_id)
        if run.stage is AcceptanceStage.RUNTIME_VERIFIED:
            if any(item.human_acceptance_required for item in run.capabilities if item.locked):
                raise RuntimeAcceptanceError("Explicit human acceptance is required")
        elif run.stage is AcceptanceStage.HUMAN_ACCEPTANCE_REQUIRED:
            required = {
                item.capability_id
                for item in run.capabilities
                if item.locked and item.human_acceptance_required
            }
            decisions = {
                item.capability_id: item.decision for item in run.human_acceptances
            }
            if required - decisions.keys() or any(
                decisions[item] != "ACCEPT" for item in required
            ):
                raise RuntimeAcceptanceError("All required human gates must be accepted")
        else:
            raise RuntimeAcceptanceError("Runtime verification is required before acceptance")
        report = validate_completeness(run)
        if not report.complete:
            raise RuntimeAcceptanceError(
                "Capability completeness blocks acceptance: " + ", ".join(report.blockers)
            )
        value = replace(run, evidence_digest=report.evidence_digest, blockers=())
        value = transition(value, AcceptanceStage.ACCEPTED, now)
        return self._save(value, "RUNTIME_ACCEPTANCE_ACCEPTED")

    def complete(self, product_id: str, run_id: str, now: datetime) -> RuntimeAcceptanceRun:
        run = self._load(product_id, run_id)
        report = validate_completeness(run)
        if not report.complete:
            raise RuntimeAcceptanceError("Incomplete acceptance cannot be completed")
        return self._advance(product_id, run_id, AcceptanceStage.COMPLETED, now)

    def report(self, product_id: str, run_id: str):
        return validate_completeness(self._load(product_id, run_id))

    def _advance(
        self,
        product_id: str,
        run_id: str,
        target: AcceptanceStage,
        now: datetime,
    ) -> RuntimeAcceptanceRun:
        value = transition(self._load(product_id, run_id), target, now)
        return self._save(value, f"RUNTIME_ACCEPTANCE_{target.value}")

    def _load(self, product_id: str, run_id: str) -> RuntimeAcceptanceRun:
        run = self.store.load(product_id, run_id)
        if run is None:
            raise RuntimeAcceptanceError("Unknown runtime acceptance run")
        return run

    @staticmethod
    def _validate_evidence(
        run: RuntimeAcceptanceRun, evidence: tuple[EvidenceArtifact, ...]
    ) -> None:
        existing = {item.evidence_id for item in run.evidence}
        supplied: set[str] = set()
        for item in evidence:
            if item.run_id != run.run_id:
                raise RuntimeAcceptanceError("Evidence belongs to another run")
            if item.commit_sha != run.commit_sha:
                raise RuntimeAcceptanceError("Evidence is stale for the current commit")
            if item.evidence_id in existing or item.evidence_id in supplied:
                raise RuntimeAcceptanceError("Evidence IDs must be immutable and unique")
            supplied.add(item.evidence_id)

    def _save(self, run: RuntimeAcceptanceRun, event: str) -> RuntimeAcceptanceRun:
        self.store.save(run)
        self._event(event, run)
        return run

    def _event(self, name: str, run: RuntimeAcceptanceRun) -> None:
        if self.event_publisher is not None:
            from runtime.events.types import EventType

            self.event_publisher.publish(
                EventType(name),
                "RUNTIME_ACCEPTANCE",
                run.run_id,
                {
                    "product_id": run.product_id,
                    "commit_sha": run.commit_sha,
                    "stage": run.stage.value,
                },
            )
