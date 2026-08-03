# System Architecture

The outbox separates durable intent, claim/dispatch, provider execution, local
result application, reconciliation, and operator control. Provider calls occur
outside rollbackable local transactions. Workers are explicit runtime objects,
not automatically started services.

External execution is split into tool, workspace, Git, GitHub, coding-agent,
and task-coordination boundaries. Domain services never import subprocess,
SQLite, GitHub SDK, OpenAI SDK, or operating-system shell details. Coding-agent
providers are execution infrastructure and are intentionally distinct from
software-company domain agents.

`DatabasePersistenceProvider` is composed through the provider-neutral
persistence boundary. It owns SQL, migrations, optimistic versions, and
optional leases; no database model leaks into domain services. A PostgreSQL
provider can therefore preserve domain contracts.

`ASCOSRuntimeContainer` is the composition root. Its default configuration is
fully in-memory. Optional persistence adds `RuntimePersistenceService` and a
caller-supplied `PersistenceProvider`; no singleton or hard-coded path exists.

The domain graph remains RuntimeEngine → AgentRegistry → Orchestrator →
ExecutionService/ExecutionRecoveryService → SoftwareDeliveryWorkflowService.
One EventStore, EventPublisher, and transaction coordinator are shared.

Persistence observes successful workflow boundaries through a post-transaction
callback. Explicit saves are always available. Capture and restoration live
outside domain models, preserving the provider-neutral boundary.

The file provider is a development and test implementation. A future database
provider can implement checkpoint, state, event, and persistence-transaction
contracts while preserving checkpoint schema and integrity validation.

Human-reviewed product delivery is the default product-level control loop. It
links knowledge capture, implementation planning, optional provider dispatch,
verification, recorded human review, explicit merge authorization, and next
milestone creation. See [Human-Reviewed Product Delivery](HUMAN_REVIEWED_PRODUCT_DELIVERY.md).
# Milestone 13.0 human-reviewed product delivery

Human-reviewed product delivery is the default operating model. The product
delivery domain separates provider execution, verification, human review, merge
authorization, and merge into explicit persisted transitions. See
`HUMAN_REVIEWED_PRODUCT_DELIVERY.md` for lifecycle, execution modes, persistence,
dashboard, and adapter boundaries.

# Milestone 11.3F runtime boundary

Explicit spawned workers reconstruct dependencies from safe references. Worker
registration and heartbeat persistence are separate from outbox claim ownership and
fencing. Provider health and deterministic routing are provider-neutral services.
PostgreSQL-specific migrations, transactions, and locking remain isolated beneath
the persistence adapter; SQLite remains the local-development provider.
