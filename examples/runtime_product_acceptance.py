"""Executable exact-commit runtime acceptance lifecycle example."""

from datetime import datetime, timezone
import hashlib
from pathlib import Path
import sys
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from runtime.runtime_acceptance import *  # noqa: F403

NOW = datetime(2026, 8, 7, tzinfo=timezone.utc)
SHA = "a" * 40


def artifact(kind: EvidenceKind) -> EvidenceArtifact:
    identity = kind.value.lower()
    return EvidenceArtifact(
        identity,
        "demo-run",
        "DEMO",
        "demo.customer_journey",
        kind,
        EvidenceOutcome.PASS,
        SHA,
        f"artifact://{identity}",
        hashlib.sha256(identity.encode()).hexdigest(),
        NOW,
        f"Verified {kind.value}",
    )


def main() -> None:
    capability = CapabilityAcceptanceContract(
        "DEMO", "1.0", "Complete demo journey", ("demo.customer_journey",)
    )
    required = (
        EvidenceKind.BROWSER,
        EvidenceKind.BROWSER_CONSOLE,
        EvidenceKind.BROWSER_NETWORK,
        EvidenceKind.SCREENSHOT,
        EvidenceKind.PERSISTENCE,
        EvidenceKind.SECURITY,
    )
    journey = AcceptanceJourney(
        "demo.customer_journey", "DEMO", "Customer completes the demo", required
    )
    planned = RuntimeAcceptanceRun(
        "demo-run",
        "demo-product",
        "1.0",
        SHA,
        AcceptanceStage.PLANNED,
        (capability,),
        (journey,),
        NOW,
        NOW,
    )
    with TemporaryDirectory() as root:
        service = RuntimeAcceptanceService(RuntimeAcceptanceStore(root))
        value = service.mark_implemented("demo-product", service.plan(planned).run_id, NOW)
        automated = (artifact(EvidenceKind.CODE), artifact(EvidenceKind.AUTOMATED_TEST))
        value = service.record_automated_verification(
            value.product_id, value.run_id, automated, NOW
        )
        runtime_kinds = set(required) | {
            EvidenceKind.SERVICE_STARTUP,
            EvidenceKind.READINESS,
            EvidenceKind.MIGRATION,
        }
        evidence = tuple(artifact(kind) for kind in sorted(runtime_kinds, key=lambda x: x.value))
        result = JourneyResult(
            journey.journey_id,
            EvidenceOutcome.PASS,
            tuple(item.evidence_id for item in evidence),
            NOW,
        )
        value = service.record_runtime_verification(
            value.product_id, value.run_id, evidence, (result,), NOW
        )
        value = service.accept(value.product_id, value.run_id, NOW)
        value = service.complete(value.product_id, value.run_id, NOW)
        print(value.stage.value, value.commit_sha, value.evidence_digest)


if __name__ == "__main__":
    main()
