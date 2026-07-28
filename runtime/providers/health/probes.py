class ProviderProbeService:
    def __init__(self, circuit_breaker, probes):
        self.circuit_breaker = circuit_breaker
        self.probes = probes

    def probe(self, provider_id, capability):
        self.circuit_breaker.allow(provider_id, capability)
        try:
            result = bool(self.probes[provider_id]())
        except Exception:
            self.circuit_breaker.failure(
                provider_id, capability, category="PROBE", code="PROBE_FAILED"
            )
            return False
        if result:
            self.circuit_breaker.success(provider_id, capability)
        else:
            self.circuit_breaker.failure(
                provider_id, capability, category="PROBE", code="UNHEALTHY"
            )
        return result
