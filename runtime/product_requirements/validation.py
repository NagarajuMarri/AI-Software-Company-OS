"""Deterministic requirement completeness, duplicate, and conflict validation."""

from collections import defaultdict

from runtime.product_requirements.models import (
    ProductRequirement, ProductRequirementsDocument, RequirementStatus, ValidationIssue,
)


def validate_requirements(requirements: tuple[ProductRequirement, ...]) -> tuple[ValidationIssue, ...]:
    issues: list[ValidationIssue] = []
    by_title: dict[str, list[str]] = defaultdict(list)
    known_ids = {item.requirement_id for item in requirements}
    for item in requirements:
        by_title[_normal(item.title)].append(item.requirement_id)
        if not item.acceptance_criteria:
            issues.append(ValidationIssue("MISSING_ACCEPTANCE_CRITERIA", "Acceptance criteria are required", (item.requirement_id,)))
        if not item.rationale.strip():
            issues.append(ValidationIssue("MISSING_RATIONALE", "Rationale is required", (item.requirement_id,)))
        if not item.milestone.strip():
            issues.append(ValidationIssue("MISSING_MILESTONE", "Milestone is required", (item.requirement_id,)))
        if item.status in {RequirementStatus.APPROVED, RequirementStatus.LOCKED,
                           RequirementStatus.IMPLEMENTED} and not item.approver:
            issues.append(ValidationIssue("MISSING_APPROVAL", "Approval is required", (item.requirement_id,)))
        for conflict in item.conflicts_with:
            if conflict not in known_ids:
                issues.append(ValidationIssue("UNKNOWN_CONFLICT", "Conflict target is unknown", (item.requirement_id, conflict)))
            elif item.requirement_id < conflict:
                issues.append(ValidationIssue("CONFLICTING_REQUIREMENTS", "Requirements explicitly conflict", (item.requirement_id, conflict)))
    for ids in by_title.values():
        if len(ids) > 1:
            issues.append(ValidationIssue("DUPLICATE_REQUIREMENT", "Requirements have duplicate normalized titles", tuple(ids)))
    return tuple(sorted(issues, key=lambda issue: (issue.code, issue.requirement_ids)))


def validate_prd(prd: ProductRequirementsDocument) -> tuple[ValidationIssue, ...]:
    issues = list(validate_requirements(prd.requirements))
    if prd.status in {RequirementStatus.APPROVED, RequirementStatus.LOCKED} and not prd.approver:
        issues.append(ValidationIssue("MISSING_PRD_APPROVAL", "Approved PRD requires an approver"))
    return tuple(sorted(issues, key=lambda issue: (issue.code, issue.requirement_ids)))


def _normal(value: str) -> str:
    return " ".join(value.casefold().split())
