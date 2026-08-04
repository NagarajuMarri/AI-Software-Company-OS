"""Application service for governed Product Requirements Management."""

from dataclasses import replace
from datetime import datetime

from runtime.product_requirements.lifecycle import revision, transition_requirement
from runtime.product_requirements.models import *  # noqa: F403
from runtime.product_requirements.persistence import ProductRequirementsStore
from runtime.product_requirements.validation import validate_prd


class ProductRequirementsService:
    def __init__(self, store: ProductRequirementsStore, project_registry=None, event_publisher=None) -> None:
        self.store = store
        self.project_registry = project_registry
        self.event_publisher = event_publisher

    def create_prd(self, prd: ProductRequirementsDocument) -> ProductRequirementsDocument:
        if prd.status is not RequirementStatus.DRAFT: raise ValueError("New PRDs start as DRAFT")
        if self.project_registry is not None: self.project_registry.get(prd.product_id)
        self._clean(prd); self.store.save_prd(prd); self._event("REQUIREMENT_PRD_CREATED", prd); return prd

    def submit_for_review(self, prd: ProductRequirementsDocument, actor: str, now: datetime) -> ProductRequirementsDocument:
        return self._transition(prd, RequirementStatus.REVIEW, actor, "Submitted for review", now)

    def approve(self, prd: ProductRequirementsDocument, approver: str, now: datetime) -> ProductRequirementsDocument:
        if prd.status is not RequirementStatus.UNDER_REVIEW: raise ValueError("Only reviewed PRDs can be approved")
        requirements = tuple(transition_requirement(item, RequirementStatus.APPROVED, approver, now) for item in prd.requirements)
        value = replace(prd, status=RequirementStatus.APPROVED, approver=approver, requirements=requirements,
                        updated_at=now, revision_history=prd.revision_history + (revision(prd.version, approver, "APPROVED", "Human approval", now),))
        self._clean(value); self.store.save_prd(value); self._event("REQUIREMENT_PRD_APPROVED", value); return value

    def lock(self, prd: ProductRequirementsDocument, approver: str, now: datetime) -> ProductRequirementsDocument:
        if prd.status is not RequirementStatus.APPROVED or prd.approver != approver: raise ValueError("Only the recorded approver can lock an approved PRD")
        requirements = tuple(transition_requirement(item, RequirementStatus.LOCKED, approver, now) for item in prd.requirements)
        value = replace(prd, status=RequirementStatus.LOCKED, requirements=requirements, locked_at=now,
                        updated_at=now, revision_history=prd.revision_history + (revision(prd.version, approver, "LOCKED", "Approved requirements frozen", now),))
        self._clean(value); self.store.save_prd(value); self._event("REQUIREMENT_PRD_LOCKED", value); return value

    def revise(self, prd: ProductRequirementsDocument, version: str, author: str, reason: str, now: datetime) -> ProductRequirementsDocument:
        if prd.status not in {RequirementStatus.LOCKED, RequirementStatus.IMPLEMENTED}: raise ValueError("Only governed PRDs can be revised")
        requirements = tuple(replace(item, version=version, status=RequirementStatus.DRAFT, approver=None,
                                     author=author, updated_at=now, created_at=now) for item in prd.requirements)
        value = replace(prd, version=version, status=RequirementStatus.DRAFT, author=author, approver=None,
                        requirements=requirements, supersedes_version=prd.version, locked_at=None,
                        created_at=now, updated_at=now,
                        revision_history=prd.revision_history + (revision(version, author, "REVISED", reason, now),))
        self.store.save_prd(value); return value

    def supersede(self, prd: ProductRequirementsDocument, actor: str, reason: str, now: datetime) -> ProductRequirementsDocument:
        if prd.status not in {RequirementStatus.APPROVED, RequirementStatus.LOCKED, RequirementStatus.IMPLEMENTED}: raise ValueError("PRD cannot be superseded")
        requirements = tuple(replace(item, status=RequirementStatus.SUPERSEDED, updated_at=now) for item in prd.requirements)
        value = replace(prd, status=RequirementStatus.SUPERSEDED, requirements=requirements, updated_at=now,
                        revision_history=prd.revision_history + (revision(prd.version, actor, "SUPERSEDED", reason, now),))
        self.store.save_prd(value); return value

    @staticmethod
    def diff(old: ProductRequirementsDocument, new: ProductRequirementsDocument) -> RequirementDiff:
        before={item.requirement_id:item for item in old.requirements}; after={item.requirement_id:item for item in new.requirements}
        return RequirementDiff(old.prd_id, old.version, new.version, tuple(sorted(after.keys()-before.keys())),
                               tuple(sorted(before.keys()-after.keys())), tuple(sorted(key for key in before.keys()&after.keys() if before[key]!=after[key])))

    @staticmethod
    def roadmap(prd: ProductRequirementsDocument) -> tuple[RoadmapMilestone, ...]:
        groups: dict[str, list[ProductRequirement]] = {}
        for item in prd.requirements:
            if item.status in {RequirementStatus.APPROVED, RequirementStatus.LOCKED}:
                groups.setdefault(item.milestone, []).append(item)
        return tuple(RoadmapMilestone(name, tuple(x.requirement_id for x in sorted(items, key=lambda x:x.requirement_id)),
                                      tuple(x.priority for x in sorted(items, key=lambda x:x.requirement_id))) for name,items in sorted(groups.items()))

    @staticmethod
    def roadmap_items(prd: ProductRequirementsDocument) -> tuple[RoadmapItem, ...]:
        return tuple(RoadmapItem(f"roadmap-{prd.product_id}-{index:03d}", prd.product_id,
                                 milestone.milestone, milestone.requirement_ids)
                     for index, milestone in enumerate(ProductRequirementsService.roadmap(prd), 1))

    def trace_implementation(self, prd: ProductRequirementsDocument, trace: ImplementationTrace) -> ImplementationTrace:
        requirement = next((item for item in prd.requirements if item.requirement_id == trace.requirement_id), None)
        if requirement is None: raise ValueError("Trace requirement is not in the PRD")
        if requirement.status not in {RequirementStatus.APPROVED, RequirementStatus.LOCKED, RequirementStatus.IMPLEMENTED}: raise ValueError("Implementation requires an approved requirement")
        self.store.save_trace(prd.product_id, trace); return trace

    def query_traces(self, product_id: str, *, requirement_id: str | None = None,
                     task_id: str | None = None, implementation_id: str | None = None,
                     commit_sha: str | None = None, pull_request_url: str | None = None,
                     release_id: str | None = None) -> tuple[ImplementationTrace, ...]:
        filters = {"requirement_id": requirement_id, "implementation_task_id": task_id,
                   "implementation_id": implementation_id, "commit_sha": commit_sha,
                   "pull_request_url": pull_request_url, "release_id": release_id}
        return tuple(trace for trace in self.store.list_traces(product_id)
                     if all(value is None or getattr(trace, field) == value for field, value in filters.items()))

    def create_change_request(self, request: RequirementChangeRequest) -> RequirementChangeRequest:
        known = {item.requirement_id for prd in self.store.list_product_prds(request.product_id) for item in prd.requirements}
        if not set(request.requirement_ids) <= known: raise ValueError("Change request references unknown requirements")
        self.store.save_change_request(request); return request

    def validate_implementation_request(self, prd: ProductRequirementsDocument,
                                        requirement_ids: tuple[str, ...]) -> None:
        if not requirement_ids: raise ValueError("Implementation must reference requirements")
        requirements = {item.requirement_id: item for item in prd.requirements}
        if any(item not in requirements for item in requirement_ids): raise ValueError("Implementation references unknown requirement")
        if any(requirements[item].status is not RequirementStatus.LOCKED for item in requirement_ids):
            raise ValueError("Implementation requests require LOCKED requirements")

    def record_decision(self, product_id: str, entry: DecisionLogEntry) -> DecisionLogEntry:
        if entry.product_id and entry.product_id != product_id: raise ValueError("Decision product mismatch")
        if not entry.approver: raise ValueError("Decision approver is required")
        self.store.save_decision(product_id, entry); return entry

    def decision_history(self, product_id: str, requirement_id: str | None = None) -> tuple[DecisionLogEntry, ...]:
        values = self.store.list_decisions(product_id)
        return tuple(item for item in values if requirement_id is None or requirement_id in item.affected_requirements)

    def _transition(self, prd: ProductRequirementsDocument, target: RequirementStatus, actor: str, reason: str, now: datetime) -> ProductRequirementsDocument:
        requirements=tuple(transition_requirement(item,target,actor,now) for item in prd.requirements)
        value=replace(prd,status=target,requirements=requirements,updated_at=now,
                      revision_history=prd.revision_history+(revision(prd.version,actor,target.value,reason,now),))
        self.store.save_prd(value); return value

    @staticmethod
    def _clean(prd: ProductRequirementsDocument) -> None:
        issues=validate_prd(prd)
        if issues: raise ValueError("; ".join(f"{item.code}: {item.message}" for item in issues))

    def _event(self, event_name: str, prd: ProductRequirementsDocument) -> None:
        if self.event_publisher is not None:
            from runtime.events.types import EventType
            self.event_publisher.publish(EventType(event_name), "PRODUCT_REQUIREMENTS_DOCUMENT", prd.prd_id,
                                         {"product_id": prd.product_id, "version": prd.version, "status": prd.status.value})
