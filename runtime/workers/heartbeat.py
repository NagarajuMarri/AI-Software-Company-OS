class HeartbeatService:
    def __init__(self, registry, *, timeout_seconds):
        self.registry = registry
        self.timeout_seconds = timeout_seconds
    def record(self, instance_id):
        return self.registry.heartbeat(
            instance_id, timeout_seconds=self.timeout_seconds
        )
    def scan_stale(self): return self.registry.scan_stale()
