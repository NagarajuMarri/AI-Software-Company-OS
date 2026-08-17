# AI-Software-Company-OS (ASCOS)

Day 7 adds immutable exact-commit browser journey execution. ASCOS can now run declarative end-user
login/session journeys in Playwright Chromium while the Day 6 environment is ready, resolve approved
browser credentials only at invocation, block unapproved origins, and persist content-addressed
browser, console, network, screenshot, migration, startup, and readiness evidence. Exact retries do
not repeat effects. Production-product testing, complete capability aggregation, human acceptance,
merge, deployment, and release remain unavailable. See `docs/MANAGED_PRODUCT_BROWSER.md`.

Day 6 adds the exact-SHA Managed Product Environment lifecycle. ASCOS can now reload one persisted
runtime configuration under current policy, create a disposable detached checkout, remove remotes,
resolve approved secret references only at invocation, run migrations, start services without a
shell, verify redirect-free readiness, stop processes in reverse order, and clean the workspace.
Returned observations are bounded and secret-safe. Day 7 consumes this boundary for browser journeys;
merge, deployment, and release remain unavailable. See `docs/MANAGED_PRODUCT_ENVIRONMENT.md`.

Day 5 adds immutable, revisioned Managed Product Runtime Configuration. A registered product can now
declare its repository, branch, exact commit SHA, argument-array service commands, endpoints, public
environment, opaque secret references, and exact acceptance-profile binding before any runtime action
is authorized. This configuration boundary performs no Git, process, network, secret-resolution,
service, browser, merge, deployment, or release operation. See
`docs/MANAGED_PRODUCT_RUNTIME_CONFIGURATION.md`.

Milestone 15 adds first-class Runtime Product Acceptance. Locked capabilities now require complete,
exact-commit customer journeys with service, migration, browser, console/network, screenshot,
persistence, PWA, voice round-trip, and explicit human UX evidence as applicable. Release candidates
cannot enter review while a locked capability is only implemented or automatically verified. See
`docs/MILESTONE_15_RUNTIME_PRODUCT_ACCEPTANCE.md`.

Milestone 12.4 adds a typed durable coding-provider boundary, a fully offline
deterministic provider, and an optional explicitly authorized OpenAI Responses
API adapter. It defines the first Spoken English AI managed pilot without
modifying the live product repository. See
`docs/CODING_PROVIDER_ARCHITECTURE.md`.

Live synchronous recovery is deliberately conservative: a mandatory durable
response receipt is the only local restart authority, and the adapter does not
claim that OpenAI can search Responses by ASCOS idempotency key. Missing
receipts require operator reconciliation. Patch application is staged,
per-file checkpointed, and inspection-based rather than globally atomic.

Milestone 12.3B adds controlled managed-product execution. An approved and
materialised proposal can enter a separately approved execution plan, map to
runtime work, run in an isolated workspace with deterministic offline coding,
pass explicit change policy and quality gates, produce integrity-checked review
evidence, and—only for an explicit `CONTROLLED_WRITE` request—be committed,
pushed, and opened as a draft PR. Nothing is automatically approved, merged,
deployed, or released. See `docs/MANAGED_PRODUCT_EXECUTION.md`.

ASCOS is the engineering foundation for a reusable AI software company. This repository is intentionally not a product application. It is the long-lived governance, architecture, and operating-model backbone that future product teams will inherit.

## Mission

Provide a durable engineering foundation for building hundreds of future software products across SaaS, AI, mobile, government, FinTech, healthcare, CRM, ERP, education, and trading domains.

## Operating principles

1. Preserve platform clarity over product-specific shortcuts.
2. Favor standards that can survive a decade of change.
3. Treat security, quality, and documentation as first-class engineering disciplines.
4. Make every repository structure explainable, reusable, and easy to govern.
5. Keep the foundation minimal, explicit, and extensible.

## Current repository state

This repository now contains governance architecture, organizational architecture, engineering capability architecture, role architecture, digital twin architecture, decision architecture, skill architecture, tool architecture, knowledge architecture, and platform and delivery standards needed to support future product repository formation. The contents remain concise, reusable, and implementation-independent.

## Repository map

- [docs/MANAGED_PRODUCT_ENVIRONMENT.md](docs/MANAGED_PRODUCT_ENVIRONMENT.md) — exact-SHA disposable
  checkout, secret-safe migration/service lifecycle, readiness, shutdown, and cleanup.

- [docs/MANAGED_PRODUCT_RUNTIME_CONFIGURATION.md](docs/MANAGED_PRODUCT_RUNTIME_CONFIGURATION.md) —
  immutable exact-SHA runtime declarations, revision history, secret-safe environment policy, and
  acceptance-profile binding.

- [docs/MILESTONE_15_RUNTIME_PRODUCT_ACCEPTANCE.md](docs/MILESTONE_15_RUNTIME_PRODUCT_ACCEPTANCE.md) —
  feature acceptance gates, capability completeness, managed runtime orchestration, and release
  blocking.

Milestone 14.1 adds first-class Release Management with semantic versions, release candidates,
approvals, deterministic release notes, immutable rollback history, and end-to-end release
traceability. See `docs/RELEASE_MANAGEMENT.md`.

Milestone 14.0 adds governed Product Requirements Management: immutable requirements, versioned and
lockable PRDs, validation, roadmaps, decision logs, and requirement-to-release traceability. The
official frozen Spoken English AI PRD is
`product_requirements/spoken-english-ai/prd-v1.0.json`; see
`docs/PRODUCT_REQUIREMENTS_MANAGEMENT.md`.

- [docs/MANAGED_PRODUCT_PLANNING.md](docs/MANAGED_PRODUCT_PLANNING.md) —
  reviewed change requests, bounded planning context, proposals, approval, and
  safe project-manager materialisation.

- [docs/PROJECT_KNOWLEDGE_ENGINE.md](docs/PROJECT_KNOWLEDGE_ENGINE.md) —
  deterministic repository scanning, structural knowledge, and query APIs.

- [docs/AI_PROJECT_MANAGER.md](docs/AI_PROJECT_MANAGER.md) — deterministic
  milestones, tasks, progress, next actions, and ASCOS-controlled state.

- [docs/PROJECT_REGISTRY.md](docs/PROJECT_REGISTRY.md) — managed-product
  identity, repository routing metadata, lifecycle policy, and the first
  product registration boundary.

- [docs/DURABLE_OUTBOX.md](docs/DURABLE_OUTBOX.md) — atomic external intent,
  at-least-once dispatch, and local idempotent effects.
- [docs/WORKER_ARCHITECTURE.md](docs/WORKER_ARCHITECTURE.md),
  [docs/RECONCILIATION.md](docs/RECONCILIATION.md), and
  [docs/DEAD_LETTER_OPERATIONS.md](docs/DEAD_LETTER_OPERATIONS.md) — claims,
  crash recovery, and operator-controlled failure handling.

- [docs/EXTERNAL_TOOL_EXECUTION.md](docs/EXTERNAL_TOOL_EXECUTION.md) — safe
  commands and isolated workspaces.
- [docs/GIT_INTEGRATION.md](docs/GIT_INTEGRATION.md) and
  [docs/GITHUB_INTEGRATION.md](docs/GITHUB_INTEGRATION.md) — provider-neutral
  repository boundaries.
- [docs/CODING_AGENT_PROVIDERS.md](docs/CODING_AGENT_PROVIDERS.md) — external
  coding-provider contracts and deterministic simulation.
- [docs/EXTERNAL_TASK_LIFECYCLE.md](docs/EXTERNAL_TASK_LIFECYCLE.md) and
  [docs/HUMAN_APPROVAL.md](docs/HUMAN_APPROVAL.md) — side effects, review, and
  explicit decisions.

- [docs/DATABASE_PERSISTENCE.md](docs/DATABASE_PERSISTENCE.md) — relational
  schema, atomic commits, migrations, and deployment boundaries.
- [docs/CONCURRENCY_CONTROL.md](docs/CONCURRENCY_CONTROL.md) — optimistic
  versioning and deterministic conflict handling.
- [docs/RUNTIME_LEASES.md](docs/RUNTIME_LEASES.md) — writer leases and fencing.

- [docs/RUNTIME_PERSISTENCE.md](docs/RUNTIME_PERSISTENCE.md) — checkpoint
  architecture, integrity, restoration, and file-provider limitations.
- [docs/SYSTEM_ARCHITECTURE.md](docs/SYSTEM_ARCHITECTURE.md) — runtime
  composition and provider boundaries.
- [docs/OPERATIONS.md](docs/OPERATIONS.md) — checkpoint, backup, restore, and
  corruption-response procedures.

- [docs/engineering-assessment.md](docs/engineering-assessment.md) — engineering baseline and risk assessment.
- [docs/company-design.md](docs/company-design.md) — approved organizational source-of-truth for ASCOS.
- [docs/engineering-capability-model.md](docs/engineering-capability-model.md) — internal capability model for the Engineering Office.
- [docs/role-architecture.md](docs/role-architecture.md) — authoritative source of truth for reusable engineering business roles, scalable role tiers, capability assignments, and optional digital-twin fulfilment principles.
- [docs/digital-twin-architecture.md](docs/digital-twin-architecture.md) — the authoritative architecture describing how Business Roles are fulfilled through Digital Twins while remaining technology independent.
- [docs/decision-architecture.md](docs/decision-architecture.md) — the authoritative architecture governing how decisions are owned, authorized, delegated, traced, reviewed, and evolved throughout ASCOS.
- [docs/skill-architecture.md](docs/skill-architecture.md) — the authoritative architecture defining reusable enterprise skills, their composition, proficiency, lifecycle, governance, and assignment relationships with Business Roles and Digital Twins.
- [docs/tool-architecture.md](docs/tool-architecture.md) — the authoritative architecture defining reusable operational Tools, their classifications, specification model, relationships, composition, selection, lifecycle, governance, and boundaries with Skills and future Execution Architecture.
- [docs/knowledge-architecture.md](docs/knowledge-architecture.md) — the authoritative architecture defining organizational knowledge as a governed, reusable asset, including its classification, structure, relationships, lifecycle, governance, and contribution to ASCOS product generation.
- [docs/repository-architecture.md](docs/repository-architecture.md) — long-term repository blueprint.
- [docs/platform-standards.md](docs/platform-standards.md) — shared engineering standards for future product repositories.
- [docs/architecture-review-checklist.md](docs/architecture-review-checklist.md) — evidence required before implementation begins.
- [docs/security-baseline.md](docs/security-baseline.md) — minimum security posture for all product delivery.
- [docs/release-evidence-model.md](docs/release-evidence-model.md) — evidence-backed release policy.
- [docs/adr-template.md](docs/adr-template.md) — standard template for architectural decisions.
- [docs/adr-workflow.md](docs/adr-workflow.md) — governance workflow for decision records.
- [docs/product-repo-template.md](docs/product-repo-template.md) — default structure for future product repositories.
- [docs/constitution-framework.md](docs/constitution-framework.md) — governance framework for the ASCOS Constitution.
- [docs/constitution-index.md](docs/constitution-index.md) — chapter registry and formal Constitution inventory.
