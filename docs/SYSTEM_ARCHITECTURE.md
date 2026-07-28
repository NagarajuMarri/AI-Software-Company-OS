# System Architecture

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
