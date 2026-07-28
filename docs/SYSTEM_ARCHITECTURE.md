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
