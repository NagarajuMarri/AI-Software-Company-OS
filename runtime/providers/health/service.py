from runtime.providers.health.exceptions import OperatorAuthorizationError
from runtime.providers.health.models import ProviderHealthStatus


class ProviderHealthService:
    def __init__(self, repository, *, clock, audit=None):
        self.repository = repository
        self.clock = clock
        self.audit = audit if audit is not None else []

    def list(self): return self.repository.list()

    def disable(self, provider_id, capability, *, actor, reason):
        self._authorize(actor, reason)
        state = self.repository.get(provider_id, capability)
        version = state.version
        state.status = ProviderHealthStatus.DISABLED
        state.operator_disabled = True
        state.updated_at = self.clock()
        result = self.repository.save(state, expected_version=version)
        self._audit("DISABLE", provider_id, capability, actor, reason)
        return result

    def enable(self, provider_id, capability, *, actor, reason):
        self._authorize(actor, reason)
        state = self.repository.get(provider_id, capability)
        version = state.version
        state.status = ProviderHealthStatus.UNKNOWN
        state.operator_disabled = False
        state.updated_at = self.clock()
        result = self.repository.save(state, expected_version=version)
        self._audit("ENABLE", provider_id, capability, actor, reason)
        return result

    def reset_circuit(self, provider_id, capability, *, actor, reason):
        self._authorize(actor, reason)
        state = self.repository.get(provider_id, capability)
        if state.operator_disabled:
            raise OperatorAuthorizationError("Disabled provider must be enabled explicitly")
        version = state.version
        state.status = ProviderHealthStatus.UNKNOWN
        state.consecutive_failures = 0
        state.consecutive_successes = 0
        state.open_until = None
        state.half_open_probe_count = 0
        state.updated_at = self.clock()
        result = self.repository.save(state, expected_version=version)
        self._audit("RESET_CIRCUIT", provider_id, capability, actor, reason)
        return result

    @staticmethod
    def _authorize(actor, reason):
        if not actor or not reason or len(actor) > 128 or len(reason) > 512:
            raise OperatorAuthorizationError("Operator identity and reason are required")

    def _audit(self, action, provider, capability, actor, reason):
        self.audit.append({
            "action": action, "provider_id": provider, "capability": capability,
            "actor": actor, "reason": reason, "timestamp": self.clock().isoformat(),
        })
