# Process Workers

Workers are explicit, operator-started processes. Serializable `WorkerConfiguration`
contains safe references only; clients and connections are composed inside the child.
No import starts a process, thread, provider call, or operation claim.

`ProcessOutboxWorker` registers a unique instance, heartbeats, runs bounded cycles,
observes shutdown, and records `STOPPED` or `FAILED`. Spawned processes are non-daemon
and use the cross-platform `spawn` context.
