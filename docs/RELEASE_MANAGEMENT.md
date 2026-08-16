# Release Management

Milestone 14.1 makes releases first-class ASCOS objects. `runtime.release_management` provides
semantic versions, stable and hotfix releases, release candidates, approvals, deterministic notes,
changelogs, artifacts, decisions, deployment evidence, rollback records, comparisons, superseding,
and provider-neutral atomic persistence.

The controlled lifecycle is `PLANNED -> RELEASE_CANDIDATE -> UNDER_REVIEW -> APPROVED -> RELEASED ->
ROLLED_BACK -> SUPERSEDED -> ARCHIVED`. Invalid transitions fail. Publication requires human approval
and generated release notes. Released snapshots and rollback history are immutable and never deleted.

Release notes are deterministically derived from approved requirements, merged milestones, full
commit SHAs, pull request URLs, and approved decision IDs. Queries answer what changed in a version,
which requirements shipped, and which pull requests belong to the release. Release records link those
inputs to managed product IDs without invoking deployment providers or modifying managed products.
