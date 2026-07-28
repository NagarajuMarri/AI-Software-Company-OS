# Worker Heartbeats

Heartbeats use an injected UTC clock and extend a configured expiry. Scans treat the
expiry boundary as stale and ignore terminal workers. File and SQLite registries
preserve registration and heartbeat state. Errors never include connection secrets.
