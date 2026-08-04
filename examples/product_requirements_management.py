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
        trace = service.trace_implementation(locked, ImplementationTrace(
            "trace-1", "demo-req-1", "task-1", "a" * 40,
            "https://example.test/pull/1", "release-1", NOW,
        ))
        print(f"create PRD: {created.status.value}")
        print(f"approve PRD: {approved.status.value}")
        print(f"lock PRD: {locked.status.value}")
        print(f"generate roadmap: {roadmap[0].milestone}")
        print(f"trace implementation: {trace.requirement_id} -> {trace.release_id}")


if __name__ == "__main__":
    main()
