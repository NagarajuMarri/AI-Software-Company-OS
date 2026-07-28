# Worker Architecture

Workers are explicitly constructed and run; imports and runtime composition
start no thread. A cycle claims one eligible operation, resolves an allow-listed
handler/provider, marks dispatching, invokes the provider, validates the typed
result, applies it idempotently, and records the final transition.

The deterministic supervisor runs bounded cycles and reports availability,
last success, active claims, backlog, dead-letter count, and reconciliation
count. Distributed schedulers and queues are outside this milestone.
