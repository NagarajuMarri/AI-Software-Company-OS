class ProviderRegistry:
    def __init__(self): self._providers = {}
    def register(self, provider):
        if provider.provider_id in self._providers:
            raise ValueError("Duplicate dispatch provider")
        self._providers[provider.provider_id] = provider
        return provider
    def get(self, provider_id):
        if provider_id not in self._providers:
            raise KeyError("Dispatch provider not found")
        return self._providers[provider_id]
    def available(self): return bool(self._providers)


class DeterministicDispatchProvider:
    def __init__(self, provider_id="deterministic", outcomes=()):
        self.provider_id = provider_id
        self._outcomes = list(outcomes)
        self.calls = []
        self._results = {}

    def supports(self, capability):
        return capability == "dispatch"

    def dispatch(self, operation_type, payload, *, idempotency_key):
        from runtime.operations.handlers import ProviderDispatchResult
        if idempotency_key in self._results:
            return self._results[idempotency_key]
        self.calls.append((operation_type, idempotency_key))
        if self._outcomes:
            outcome = self._outcomes.pop(0)
            if isinstance(outcome, Exception): raise outcome
        operation_id = payload.get("operation_id")
        result = ProviderDispatchResult(
            operation_id, self.provider_id,
            f"{self.provider_id}:{idempotency_key}",
            {"accepted": True},
        )
        self._results[idempotency_key] = result
        return result

    def reconcile(self, idempotency_key):
        return self._results.get(idempotency_key)
