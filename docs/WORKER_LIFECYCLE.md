# Worker Lifecycle

The lifecycle is `STARTING` to `IDLE`, with claiming, dispatching, and reconciling
work states. Shutdown moves through `STOPPING` to `STOPPED`; expiry produces `STALE`.
Worker identity differs from process and claim identity. Restarts create a new random
instance identity, while claim fencing remains the final authority for result writes.
