# Product Requirements Management

Milestone 14.0 makes requirements first-class ASCOS managed objects. The
`runtime.product_requirements` package provides immutable requirement and PRD models, controlled
lifecycle transitions, approval and lock gates, version-preserving JSON persistence, revision and
supersession history, deterministic version diffs, validation, roadmap derivation, decision logs,
and implementation traceability.

## Governance

The lifecycle is `DRAFT → REVIEW → APPROVED → LOCKED → IMPLEMENTED → SUPERSEDED → ARCHIVED`.
Review may return to draft; implemented or locked requirements may be superseded, and superseded
requirements may be archived. Invalid transitions are rejected. A PRD cannot be approved or locked
without a named human approver, and locked versions are immutable except for an explicit superseding
transition.

Implementation planning must resolve requirement IDs from an approved, locked, or implemented PRD.
The trace record then binds requirement → implementation task → full commit SHA → pull request →
release. Roadmaps contain only governed requirements and group them by milestone.

## Validation

Validation reports stable issue codes for duplicate normalized titles, explicit requirement
conflicts, missing acceptance criteria, rationale, milestone, approval, and unknown conflict targets.
Stores use safe identifiers and atomic UTF-8 JSON replacement. Every PRD version has a distinct
path and locked versions cannot be silently rewritten.

## Official Spoken English baseline

The official frozen artifact is
`product_requirements/spoken-english-ai/prd-v1.0.json`. It is version `1.0`, status `LOCKED`, and
contains the approved MVP requirements, explicit exclusions, and future roadmap. Product Milestone
9 remains planning-only; this milestone does not modify the Spoken English product repository.

Run `python examples/product_requirements_management.py` for a deterministic create, review,
approve, lock, roadmap, and trace walkthrough.
