# Product Requirements Management

Milestone 14.0 makes requirements first-class ASCOS managed objects. The
`runtime.product_requirements` package provides immutable requirement and PRD models, controlled
lifecycle transitions, approval and lock gates, version-preserving JSON persistence, revision and
supersession history, deterministic version diffs, validation, roadmap derivation, decision logs,
and implementation traceability.

## Governance

The lifecycle is `DRAFT -> UNDER_REVIEW -> APPROVED -> LOCKED -> IMPLEMENTED -> SUPERSEDED ->
ARCHIVED`. Review may return to draft. Invalid transitions fail. Locked released versions are
immutable, while changes proceed through a persisted change request and a new PRD version.

Implementation planning must resolve requirement IDs from a locked PRD and a derived roadmap item.
The trace binds requirement -> task -> implementation -> commit -> pull request -> release. Queries
can start from any link and resolve the chain in either direction. Roadmaps contain only approved or
locked requirements and group them by milestone.

The domain persists requirement groups, approvals, locks, version evidence, change requests,
decision records, and roadmap items. The managed-product pipeline can enforce PRD and roadmap
references before workspace preparation. The service verifies products through the project registry
and emits PRD create, approve, and lock events through the runtime event publisher. Atomic,
provider-neutral files support restart recovery and checkpoint-safe reconstruction.

## Validation

Validation reports stable issue codes for duplicate normalized titles, explicit conflicts, circular
superseding, missing acceptance criteria, rationale, milestone or approval, unlocked implementation
requests, and unknown conflict targets. Stores use safe identifiers and atomic UTF-8 JSON
replacement.

## Official Spoken English baseline

The official frozen artifact is `product_requirements/spoken-english-ai/prd-v1.0.json`. It is
version `1.0`, status `LOCKED`, and contains the approved MVP requirements, explicit exclusions,
requirement groups, approval evidence, and future roadmap. Product Milestone 9 remains
planning-only; this milestone does not modify the Spoken English product repository.

Run `python examples/product_requirements_management.py` for a deterministic create, review,
approve, lock, compare, roadmap, trace, and decision-history walkthrough.
