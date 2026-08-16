from dataclasses import replace
from datetime import datetime, timezone

import pytest

from runtime.release_management import *

NOW=datetime(2026,1,1,tzinfo=timezone.utc)
LATER=datetime(2026,1,2,tzinfo=timezone.utc)


def release(**changes):
    values=dict(release_id="release-1",product_ids=("product",),version=Version.parse("1.2.0"),
                kind=ReleaseKind.STABLE,status=ReleaseStatus.PLANNED,title="Release 1.2",
                created_by="owner",created_at=NOW,updated_at=NOW,requirement_ids=("req-1",),
                milestone_ids=("milestone-14",),commit_shas=("a"*40,),
                pull_request_urls=("https://example.test/pr/1",),decision_ids=("decision-1",))
    values.update(changes); return Release(**values)


@pytest.fixture
def service(tmp_path): return ReleaseManagementService(ReleaseStore(tmp_path))


@pytest.mark.parametrize("text",["0.1.0","1.2.3","1.2.3-rc.1","10.20.30"])
def test_semantic_versions_round_trip(text): assert str(Version.parse(text)) == text


@pytest.mark.parametrize("text",["1","1.2","v1.2.3","01.2.3","1.2.3-rc","1.2.3-beta"])
def test_invalid_semantic_versions_fail(text):
    with pytest.raises(ValueError): Version.parse(text)


def candidate(): return ReleaseCandidate("rc-1",Version.parse("1.2.0-rc.1"),"a"*40,"owner",NOW)
def approval(value=None):
    value=value or release()
    return ReleaseApproval("approval-1","reviewer","APPROVE","Verified",LATER,
                           ReleaseManagementService.evidence_digest(value))


def approved(service):
    value=service.create(release())
    value=service.create_candidate(value,candidate(),LATER)
    value=service.submit(value,LATER)
    return service.approve(value,approval(value),LATER)


def test_exact_release_lifecycle():
    assert [item.value for item in ReleaseStatus] == ["PLANNED","RELEASE_CANDIDATE","UNDER_REVIEW",
        "APPROVED","RELEASED","ROLLED_BACK","SUPERSEDED","ARCHIVED"]


def test_invalid_transition_fails():
    with pytest.raises(ValueError): transition(release(),ReleaseStatus.RELEASED,LATER)


def test_candidate_review_and_approval(service):
    value=approved(service)
    assert value.status is ReleaseStatus.APPROVED and value.approvals==(approval(replace(value,approvals=())),)


def test_candidate_requires_rc_version(service):
    service.create(release())
    bad=replace(candidate(),version=Version.parse("1.2.0"))
    with pytest.raises(ValueError): service.create_candidate(release(),bad,LATER)


def test_publish_requires_approval_and_notes(service):
    with pytest.raises(ValueError): service.publish(release(),LATER)
    value=service.attach_notes(approved(service))
    published=service.publish(value,LATER)
    assert published.status is ReleaseStatus.RELEASED and published.released_at==LATER


def test_deterministic_notes_and_changelog(service):
    value=service.attach_notes(service.create(release(requirement_ids=("req-2","req-1"))))
    assert value.notes.requirements == ("req-1","req-2")
    assert value.changelog.entries == ("Requirement req-1","Requirement req-2","Milestone milestone-14")


def test_release_queries_survive_restart(service,tmp_path):
    value=service.attach_notes(service.create(release()))
    restarted=ReleaseManagementService(ReleaseStore(tmp_path))
    assert restarted.what_changed("1.2.0") == value.notes
    assert restarted.requirements_shipped("1.2.0") == ("req-1",)
    assert restarted.pull_requests_for("1.2.0") == ("https://example.test/pr/1",)


def test_compare_releases():
    newer=release(version=Version.parse("1.3.0"),requirement_ids=("req-1","req-2"),
                  commit_shas=("a"*40,"b"*40),pull_request_urls=("https://example.test/pr/1","https://example.test/pr/2"),
                  decision_ids=("decision-1","decision-2"))
    comparison=ReleaseManagementService.compare(release(),newer)
    assert comparison.added_requirements == ("req-2",) and comparison.added_commits == ("b"*40,)


def test_rollback_history_is_persisted_and_never_deleted(service):
    value=service.publish(service.attach_notes(approved(service)),LATER)
    record=RollbackRecord("rollback-1","Regression","operator","1.1.0",LATER)
    rolled=service.rollback(value,record,LATER)
    assert rolled.rollbacks == (record,)
    assert service.store.load("release-1") == rolled
    assert len(list((service.store.root/"release-1"/"snapshots").glob("*.json"))) >= 6


def test_released_snapshot_is_immutable(service):
    value=service.publish(service.attach_notes(approved(service)),LATER)
    with pytest.raises(ValueError): service.store.save(replace(value,title="Changed"))


def test_superseding_preserves_history(service):
    value=service.publish(service.attach_notes(approved(service)),LATER)
    successor=release(release_id="release-2",version=Version.parse("1.3.0"),title="Release 1.3")
    successor=service.create(successor)
    rc=replace(candidate(),candidate_id="rc-2",version=Version.parse("1.3.0-rc.1"))
    successor=service.submit(service.create_candidate(successor,rc,LATER),LATER)
    successor=service.approve(successor,approval(successor),LATER)
    service.publish(service.attach_notes(successor),LATER)
    superseded=service.supersede(value,"release-2",LATER)
    assert superseded.status is ReleaseStatus.SUPERSEDED and superseded.superseded_by=="release-2"


def test_release_supports_artifacts_decisions_deployments_and_hotfix():
    artifact=ReleaseArtifact("artifact-1","package","sha256:abc","application/zip","store://package")
    decision=ReleaseDecision("decision-1","SHIP","Verified","reviewer",("req-1",),NOW)
    deployment=DeploymentRecord("deployment-1","production","SUCCEEDED",("artifact-1",),"operator",NOW)
    value=release(kind=ReleaseKind.HOTFIX,artifacts=(artifact,),decisions=(decision,),deployments=(deployment,))
    assert value.kind is ReleaseKind.HOTFIX and value.deployments[0].artifact_ids==(artifact.artifact_id,)


def test_release_rejects_unsafe_ids_and_bad_commits(tmp_path):
    with pytest.raises(ValueError): ReleaseStore(tmp_path).load("../escape")
    with pytest.raises(ValueError): release(commit_shas=("short",))


def test_duplicate_versions_are_rejected(service):
    service.create(release())
    with pytest.raises(ValueError,match="version already exists"):
        service.create(release(release_id="release-2"))


def test_self_and_stale_approval_are_rejected(service):
    value=service.submit(service.create_candidate(service.create(release()),candidate(),LATER),LATER)
    stale=replace(approval(value),evidence_digest="0"*64)
    with pytest.raises(ValueError,match="stale"): service.approve(value,stale,LATER)
    self_approval=replace(approval(value),approver="owner")
    with pytest.raises(ValueError,match="self-approve"): service.approve(value,self_approval,LATER)


def test_rejection_requires_reason_and_records_history(service):
    value=service.submit(service.create_candidate(service.create(release()),candidate(),LATER),LATER)
    bad=ReleaseApproval("review-1","reviewer","REJECT","",LATER)
    with pytest.raises(ValueError,match="requires a reason"): service.reject(value,bad,LATER)
    decision=replace(bad,rationale="Verification failed")
    returned=service.reject(value,decision,LATER)
    assert returned.status is ReleaseStatus.RELEASE_CANDIDATE and returned.approvals==(decision,)


def test_notes_deduplicate_and_reverse_queries(service):
    value=release(requirement_ids=("req-1","req-1"),commit_shas=("a"*40,"a"*40),
                  pull_request_urls=("https://example.test/pr/1","https://example.test/pr/1"))
    service.create(value)
    assert service.generate_notes(value).requirements == ("req-1",)
    assert service.commits_for("1.2.0") == value.commit_shas
    assert service.releases_for_requirement("req-1") == (value,)
    assert service.releases_for_pull_request("https://example.test/pr/1") == (value,)


def test_stable_version_has_higher_precedence_than_candidate():
    assert Version.parse("1.0.0-rc.2") < Version.parse("1.0.0") < Version.parse("1.0.1")


def test_release_requires_utc_timestamps():
    from datetime import timedelta
    non_utc=datetime(2026,1,1,tzinfo=timezone(timedelta(hours=1)))
    with pytest.raises(ValueError,match="UTC"): release(created_at=non_utc)
