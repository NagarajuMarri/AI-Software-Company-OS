"""Capability completeness and evidence-integrity validation."""

from runtime.runtime_acceptance.models import (
    AcceptanceStage,
    CompletenessReport,
    EvidenceKind,
    EvidenceOutcome,
    RuntimeAcceptanceRun,
    evidence_digest,
)


def validate_completeness(run: RuntimeAcceptanceRun) -> CompletenessReport:
    blockers: list[str] = []
    capabilities = {item.capability_id: item for item in run.capabilities}
    journeys = {item.journey_id: item for item in run.journeys}
    results = {item.journey_id: item for item in run.journey_results}
    evidence = {item.evidence_id: item for item in run.evidence}

    global_kinds = {item.kind for item in run.evidence if item.outcome is EvidenceOutcome.PASS}
    for kind in (
        EvidenceKind.CODE,
        EvidenceKind.AUTOMATED_TEST,
        EvidenceKind.SERVICE_STARTUP,
        EvidenceKind.READINESS,
        EvidenceKind.MIGRATION,
    ):
        if kind not in global_kinds:
            blockers.append(f"MISSING_GLOBAL_{kind.value}")
    if any(item.locked and item.customer_facing for item in run.capabilities):
        for kind in (
            EvidenceKind.BROWSER,
            EvidenceKind.BROWSER_CONSOLE,
            EvidenceKind.BROWSER_NETWORK,
            EvidenceKind.SCREENSHOT,
        ):
            if kind not in global_kinds:
                blockers.append(f"MISSING_GLOBAL_{kind.value}")

    for declared_journey in run.journeys:
        if declared_journey.capability_id not in capabilities:
            blockers.append(
                "JOURNEY_UNKNOWN_CAPABILITY:"
                f"{declared_journey.journey_id}:{declared_journey.capability_id}"
            )

    for capability in run.capabilities:
        if not capability.locked:
            continue
        for journey_id in capability.required_journey_ids:
            required_journey = journeys.get(journey_id)
            if required_journey is None:
                blockers.append(
                    f"MISSING_REQUIRED_JOURNEY:{capability.capability_id}:{journey_id}"
                )
                continue
            if required_journey.capability_id != capability.capability_id:
                blockers.append(
                    f"JOURNEY_CAPABILITY_MISMATCH:{capability.capability_id}:{journey_id}"
                )
                continue
            result = results.get(journey_id)
            if result is None:
                blockers.append(
                    f"MISSING_JOURNEY_RESULT:{capability.capability_id}:{journey_id}"
                )
                continue
            if result.outcome is not EvidenceOutcome.PASS:
                blockers.append(
                    f"JOURNEY_FAILED:{capability.capability_id}:{journey_id}"
                )
            linked = [evidence.get(item) for item in result.evidence_ids]
            if any(item is None for item in linked):
                blockers.append(f"MISSING_EVIDENCE_ARTIFACT:{journey_id}")
                continue
            actual_kinds = set()
            for item in linked:
                assert item is not None
                if item.commit_sha != run.commit_sha:
                    blockers.append(f"STALE_COMMIT_EVIDENCE:{item.evidence_id}")
                if item.run_id != run.run_id or item.journey_id != journey_id:
                    blockers.append(f"MISBOUND_EVIDENCE:{item.evidence_id}")
                if item.capability_id != capability.capability_id:
                    blockers.append(f"WRONG_CAPABILITY_EVIDENCE:{item.evidence_id}")
                if item.outcome is not EvidenceOutcome.PASS:
                    blockers.append(f"FAILED_EVIDENCE:{item.evidence_id}")
                actual_kinds.add(item.kind)
            for kind in required_journey.required_evidence:
                if kind not in actual_kinds:
                    blockers.append(f"MISSING_{kind.value}:{journey_id}")

    required_human = {
        item.capability_id
        for item in run.capabilities
        if item.locked and item.human_acceptance_required
    }
    accepted_human = {
        item.capability_id
        for item in run.human_acceptances
        if item.decision == "ACCEPT"
        and item.commit_sha == run.commit_sha
        and item.evidence_digest == evidence_digest(run)
    }
    if run.stage in {AcceptanceStage.ACCEPTED, AcceptanceStage.COMPLETED}:
        for capability_id in sorted(required_human - accepted_human):
            blockers.append(f"MISSING_HUMAN_ACCEPTANCE:{capability_id}")

    unique = tuple(sorted(set(blockers)))
    return CompletenessReport(
        not unique,
        unique,
        tuple(sorted(capabilities)),
        evidence_digest(run),
    )
