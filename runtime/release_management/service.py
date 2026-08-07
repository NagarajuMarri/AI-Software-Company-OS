"""Release planning, approval, publication, rollback, notes, and queries."""

from dataclasses import replace
from datetime import datetime
import hashlib
import json

from runtime.release_management.lifecycle import transition
from runtime.release_management.models import *  # noqa: F403
from runtime.release_management.persistence import ReleaseStore


class ReleaseManagementService:
    def __init__(self, store: ReleaseStore, project_registry=None, event_publisher=None,
                 runtime_acceptance_store=None) -> None:
        self.store, self.project_registry, self.event_publisher = store, project_registry, event_publisher
        self.runtime_acceptance_store = runtime_acceptance_store

    def create(self, release: Release) -> Release:
        if release.status is not ReleaseStatus.PLANNED: raise ValueError("New releases start PLANNED")
        if self.store.load(release.release_id): raise ValueError("Release already exists")
        if any(item.version == release.version for item in self.store.list_releases()):
            raise ValueError("Release version already exists")
        if self.project_registry is not None:
            for product_id in release.product_ids: self.project_registry.get(product_id)
        self.store.save(release); self._event("RELEASE_PLANNED",release); return release

    def create_candidate(self, release: Release, candidate: ReleaseCandidate, now: datetime) -> Release:
        if candidate.version.release_candidate is None: raise ValueError("Candidate version requires -rc.N")
        value=transition(replace(release,candidates=release.candidates+(candidate,)),ReleaseStatus.RELEASE_CANDIDATE,now)
        self.store.save(value); return value

    def submit(self, release: Release, now: datetime) -> Release:
        self._require_runtime_acceptance(release)
        value=transition(release,ReleaseStatus.UNDER_REVIEW,now); self.store.save(value); return value

    def approve(self, release: Release, approval: ReleaseApproval, now: datetime,
                *, allow_self_approval: bool = False) -> Release:
        self._require_runtime_acceptance(release)
        if approval.decision != "APPROVE": raise ValueError("Approval decision must be APPROVE")
        if not approval.approver.strip() or not approval.rationale.strip(): raise ValueError("Approver and rationale are required")
        if approval.approver.casefold()==release.created_by.casefold() and not allow_self_approval:
            raise ValueError("Release creator cannot self-approve")
        if approval.evidence_digest != self.evidence_digest(release): raise ValueError("Approval evidence is stale")
        value=transition(replace(release,approvals=release.approvals+(approval,)),ReleaseStatus.APPROVED,now)
        self.store.save(value); self._event("RELEASE_APPROVED",value); return value

    def reject(self, release: Release, decision: ReleaseApproval, now: datetime) -> Release:
        if decision.decision not in {"REJECT","REQUEST_CHANGES"} or not decision.rationale.strip():
            raise ValueError("Rejection or change request requires a reason")
        if release.status is not ReleaseStatus.UNDER_REVIEW: raise ValueError("Release is not under review")
        value=replace(release,status=ReleaseStatus.RELEASE_CANDIDATE,
                      approvals=release.approvals+(decision,),updated_at=now)
        self.store.save(value); return value

    def publish(self, release: Release, now: datetime) -> Release:
        self._require_runtime_acceptance(release)
        if not release.approvals or release.notes is None: raise ValueError("Publication requires approval and release notes")
        value=transition(release,ReleaseStatus.RELEASED,now); self.store.save(value); self._event("RELEASE_PUBLISHED",value); return value

    def rollback(self, release: Release, record: RollbackRecord, now: datetime) -> Release:
        value=transition(replace(release,rollbacks=release.rollbacks+(record,)),ReleaseStatus.ROLLED_BACK,now)
        self.store.save(value); self._event("RELEASE_ROLLED_BACK",value); return value

    def supersede(self, release: Release, successor_id: str, now: datetime) -> Release:
        successor=self.store.load(successor_id)
        if successor is None or successor.status is not ReleaseStatus.RELEASED:
            raise ValueError("Successor must be a persisted released version")
        if not release.version < successor.version: raise ValueError("Successor version must increase")
        value=transition(replace(release,superseded_by=successor_id),ReleaseStatus.SUPERSEDED,now)
        self.store.save(value); return value

    @staticmethod
    def generate_notes(release: Release) -> ReleaseNotes:
        unique=lambda values: tuple(sorted(set(values)))
        return ReleaseNotes(f"Release {release.version}",f"Deterministic release {release.version}",
                            unique(release.requirement_ids),unique(release.milestone_ids),
                            unique(release.commit_shas),unique(release.pull_request_urls),
                            unique(release.decision_ids))

    def attach_notes(self, release: Release) -> Release:
        notes=self.generate_notes(release)
        entries=tuple(f"Requirement {item}" for item in notes.requirements)+tuple(f"Milestone {item}" for item in notes.milestones)
        value=replace(release,notes=notes,changelog=Changelog(entries)); self.store.save(value); return value

    @staticmethod
    def compare(old: Release, new: Release) -> ReleaseComparison:
        added=lambda before,after: tuple(sorted(set(after)-set(before)))
        return ReleaseComparison(str(old.version),str(new.version),added(old.requirement_ids,new.requirement_ids),
                                 tuple(sorted(set(old.requirement_ids)-set(new.requirement_ids))),
                                 added(old.commit_shas,new.commit_shas),added(old.pull_request_urls,new.pull_request_urls),
                                 added(old.decision_ids,new.decision_ids))

    def what_changed(self, version: str) -> ReleaseNotes:
        release=self._by_version(version)
        return release.notes or self.generate_notes(release)

    def requirements_shipped(self, version: str) -> tuple[str, ...]: return self._by_version(version).requirement_ids
    def pull_requests_for(self, version: str) -> tuple[str, ...]: return self._by_version(version).pull_request_urls
    def commits_for(self, version: str) -> tuple[str, ...]: return self._by_version(version).commit_shas
    def releases_for_requirement(self, requirement_id: str) -> tuple[Release, ...]:
        return tuple(item for item in self.store.list_releases() if requirement_id in item.requirement_ids)
    def releases_for_pull_request(self, pull_request_url: str) -> tuple[Release, ...]:
        return tuple(item for item in self.store.list_releases() if pull_request_url in item.pull_request_urls)

    @staticmethod
    def evidence_digest(release: Release) -> str:
        payload={"requirements":sorted(set(release.requirement_ids)),"milestones":sorted(set(release.milestone_ids)),
                 "commits":sorted(set(release.commit_shas)),"pull_requests":sorted(set(release.pull_request_urls)),
                 "decisions":sorted(set(release.decision_ids)),
                 "locked_capabilities":sorted(set(release.locked_capability_ids)),
                 "runtime_acceptance_runs":sorted(set(release.runtime_acceptance_run_ids)),
                 "artifacts":sorted((item.artifact_id,item.digest) for item in release.artifacts)}
        return hashlib.sha256(json.dumps(payload,sort_keys=True,separators=(",",":")).encode()).hexdigest()

    def readiness(self, release: Release) -> ReleaseReadiness:
        if not release.locked_capability_ids:
            return ReleaseReadiness(True, (), (), release.runtime_acceptance_run_ids)
        blockers: list[str] = []
        accepted: set[str] = set()
        if self.runtime_acceptance_store is None:
            blockers.append("RUNTIME_ACCEPTANCE_STORE_UNAVAILABLE")
        else:
            from runtime.runtime_acceptance.models import AcceptanceStage
            from runtime.runtime_acceptance.validation import validate_completeness

            candidate_sha = release.candidates[-1].commit_sha if release.candidates else None
            for run_id in release.runtime_acceptance_run_ids:
                run = self.runtime_acceptance_store.find(run_id)
                if run is None:
                    blockers.append(f"MISSING_RUNTIME_ACCEPTANCE:{run_id}")
                    continue
                if run.product_id not in release.product_ids:
                    blockers.append(f"WRONG_PRODUCT_RUNTIME_ACCEPTANCE:{run_id}")
                if candidate_sha is None or run.commit_sha != candidate_sha:
                    blockers.append(f"STALE_RUNTIME_ACCEPTANCE_COMMIT:{run_id}")
                if run.stage is not AcceptanceStage.COMPLETED:
                    blockers.append(f"INCOMPLETE_RUNTIME_ACCEPTANCE:{run_id}:{run.stage.value}")
                report = validate_completeness(run)
                if not report.complete or run.evidence_digest != report.evidence_digest:
                    blockers.append(f"INVALID_RUNTIME_ACCEPTANCE_EVIDENCE:{run_id}")
                else:
                    accepted.update(
                        item.capability_id for item in run.capabilities if item.locked
                    )
        for capability_id in release.locked_capability_ids:
            if capability_id not in accepted:
                blockers.append(f"UNACCEPTED_LOCKED_CAPABILITY:{capability_id}")
        unique = tuple(sorted(set(blockers)))
        return ReleaseReadiness(
            not unique,
            unique,
            tuple(sorted(accepted)),
            release.runtime_acceptance_run_ids,
        )

    def _require_runtime_acceptance(self, release: Release) -> None:
        readiness = self.readiness(release)
        if not readiness.ready:
            raise ValueError(
                "Release candidate is not runtime-ready: " + ", ".join(readiness.blockers)
            )

    def _by_version(self, version: str) -> Release:
        matches=[item for item in self.store.list_releases() if str(item.version)==version]
        if len(matches)!=1: raise ValueError("Release version was not found or is ambiguous")
        return matches[0]

    def _event(self, name: str, release: Release) -> None:
        if self.event_publisher is not None:
            from runtime.events.types import EventType
            self.event_publisher.publish(EventType(name),"RELEASE",release.release_id,
                                         {"version":str(release.version),"status":release.status.value,
                                          "product_ids":release.product_ids})
