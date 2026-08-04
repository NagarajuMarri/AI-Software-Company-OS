"""Deterministic Release Management lifecycle and query example."""

from datetime import datetime, timezone
from pathlib import Path
import sys
from tempfile import TemporaryDirectory

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from runtime.release_management import *

NOW=datetime(2026,1,1,tzinfo=timezone.utc)


def main() -> None:
    planned=Release("demo-release",("demo-product",),Version.parse("1.0.0"),ReleaseKind.STABLE,
                    ReleaseStatus.PLANNED,"Demo release","release-manager",NOW,NOW,
                    ("req-1",),("milestone-14",),("a"*40,),("https://example.test/pr/1",),("decision-1",))
    with TemporaryDirectory() as root:
        service=ReleaseManagementService(ReleaseStore(root))
        created=service.create(planned)
        candidate=service.create_candidate(created,ReleaseCandidate("rc-1",Version.parse("1.0.0-rc.1"),"a"*40,"release-manager",NOW),NOW)
        reviewed=service.submit(candidate,NOW)
        approved=service.approve(reviewed,ReleaseApproval("approval-1","human-reviewer","APPROVE","Verified",NOW),NOW)
        documented=service.attach_notes(approved)
        assert documented.notes is not None
        published=service.publish(documented,NOW)
        comparison=service.compare(replace_version(planned,"0.9.0"),published)
        rolled=service.rollback(published,RollbackRecord("rollback-1","Demonstration","operator","0.9.0",NOW),NOW)
        print(f"create release: {created.status.value}")
        print(f"approve release: {approved.status.value}")
        print(f"publish release: {published.status.value}")
        print(f"rollback release: {rolled.status.value}")
        print(f"generate release notes: {documented.notes.title}")
        print(f"compare releases: {comparison.from_version} -> {comparison.to_version}")


def replace_version(release: Release, version: str) -> Release:
    from dataclasses import replace
    return replace(release,version=Version.parse(version))


if __name__=="__main__": main()
