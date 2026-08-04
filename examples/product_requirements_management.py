"""Deterministic PRD creation, approval, locking, roadmap and trace example."""

from datetime import datetime, timezone
from pathlib import Path
import sys
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from runtime.product_requirements import *
from runtime.product_requirements.models import RevisionRecord

NOW = datetime(2026, 1, 1, tzinfo=timezone.utc)


def main() -> None:
    requirement = ProductRequirement(
        "demo-req-1", "Accessible practice", "Provide keyboard-accessible practice.",
        "Every learner needs an operable fallback.", ("Keyboard flow passes",),
        RequirementPriority.HIGH, "Demo Milestone", RequirementStatus.DRAFT, "1.0",
        "product-owner", None, NOW, NOW, ("demo-product",), ("accessibility",),
        RequirementCategory.ACCESSIBILITY,
    )
    prd = ProductRequirementsDocument(
        "demo-prd", "demo-product", "Demo PRD", "1.0", RequirementStatus.DRAFT,
        "product-owner", None, (requirement,), (), (),
        (RevisionRecord("1.0", "product-owner", "CREATED", "Initial PRD", NOW),), NOW, NOW,
    )
    with TemporaryDirectory() as root:
        service = ProductRequirementsService(ProductRequirementsStore(root))
        created = service.create_prd(prd)
        reviewed = service.submit_for_review(created, "product-owner", NOW)
        approved = service.approve(reviewed, "human-reviewer", NOW)
        locked = service.lock(approved, "human-reviewer", NOW)
        roadmap = service.roadmap(locked)
        revised = service.revise(locked, "2.0", "product-owner", "Add capability", NOW)
        comparison = service.diff(locked, revised)
        trace = service.trace_implementation(locked, ImplementationTrace(
            "trace-1", "demo-req-1", "task-1", "a" * 40,
            "https://example.test/pull/1", "release-1", NOW,
        ))
        print(f"create PRD: {created.status.value}")
        print(f"approve PRD: {approved.status.value}")
        print(f"lock PRD: {locked.status.value}")
        print(f"generate roadmap: {roadmap[0].milestone}")
        print(f"compare versions: {comparison.from_version} -> {comparison.to_version}")
        print(f"trace implementation: {trace.requirement_id} -> {trace.release_id}")
        decision = DecisionLogEntry(
            "decision-1", DecisionType.PRODUCT, "Accessible practice", "Keep keyboard fallback",
            "Learners need an operable fallback", "product-owner", ("demo-req-1",), NOW,
            "demo-product", "human-reviewer",
        )
        service.record_decision("demo-product", decision)
        print(f"query decision history: {service.decision_history('demo-product')[0].decision_id}")


if __name__ == "__main__":
    main()
