"""Controlled requirement and PRD lifecycle transitions."""

from dataclasses import replace
from datetime import datetime

from runtime.product_requirements.models import ProductRequirement, RequirementStatus, RevisionRecord

TRANSITIONS = {
    RequirementStatus.DRAFT: (RequirementStatus.UNDER_REVIEW,),
    RequirementStatus.UNDER_REVIEW: (RequirementStatus.DRAFT, RequirementStatus.APPROVED),
    RequirementStatus.APPROVED: (RequirementStatus.LOCKED, RequirementStatus.SUPERSEDED),
    RequirementStatus.LOCKED: (RequirementStatus.IMPLEMENTED, RequirementStatus.SUPERSEDED),
    RequirementStatus.IMPLEMENTED: (RequirementStatus.SUPERSEDED, RequirementStatus.ARCHIVED),
    RequirementStatus.SUPERSEDED: (RequirementStatus.ARCHIVED,),
    RequirementStatus.ARCHIVED: (),
}


def transition_requirement(requirement: ProductRequirement, target: RequirementStatus,
                           actor: str, now: datetime) -> ProductRequirement:
    if target not in TRANSITIONS[requirement.status]:
        raise ValueError(f"Invalid requirement transition: {requirement.status.value} -> {target.value}")
    approver = actor if target in {RequirementStatus.APPROVED, RequirementStatus.LOCKED} else requirement.approver
    locked_at = now if target is RequirementStatus.LOCKED else requirement.locked_at
    return replace(requirement, status=target, approver=approver, locked_at=locked_at, updated_at=now)


def revision(version: str, actor: str, action: str, reason: str, now: datetime) -> RevisionRecord:
    if not reason.strip():
        raise ValueError("Revision reason is required")
    return RevisionRecord(version, actor, action, reason, now)
