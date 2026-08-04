"""Validated Release Management lifecycle."""

from dataclasses import replace
from datetime import datetime

from runtime.release_management.models import Release, ReleaseStatus


TRANSITIONS = {
    ReleaseStatus.PLANNED: (ReleaseStatus.RELEASE_CANDIDATE,),
    ReleaseStatus.RELEASE_CANDIDATE: (ReleaseStatus.UNDER_REVIEW,),
    ReleaseStatus.UNDER_REVIEW: (ReleaseStatus.RELEASE_CANDIDATE, ReleaseStatus.APPROVED),
    ReleaseStatus.APPROVED: (ReleaseStatus.RELEASED,),
    ReleaseStatus.RELEASED: (ReleaseStatus.ROLLED_BACK, ReleaseStatus.SUPERSEDED),
    ReleaseStatus.ROLLED_BACK: (ReleaseStatus.SUPERSEDED, ReleaseStatus.ARCHIVED),
    ReleaseStatus.SUPERSEDED: (ReleaseStatus.ARCHIVED,),
    ReleaseStatus.ARCHIVED: (),
}


def transition(release: Release, target: ReleaseStatus, now: datetime) -> Release:
    if target not in TRANSITIONS[release.status]:
        raise ValueError(f"Invalid release transition: {release.status.value} -> {target.value}")
    return replace(release, status=target, updated_at=now,
                   released_at=now if target is ReleaseStatus.RELEASED else release.released_at)
