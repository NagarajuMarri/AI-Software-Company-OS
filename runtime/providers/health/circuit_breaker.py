from datetime import timedelta

from runtime.providers.health.exceptions import ProviderUnavailableError
from runtime.providers.health.models import ProviderHealthStatus


class CircuitBreaker:
    def __init__(
        self, repository, *, clock, failure_threshold=3,
        success_threshold=1, open_seconds=30, maximum_half_open_probes=1,
    ):
        if min(failure_threshold, success_threshold, maximum_half_open_probes) < 1:
            raise ValueError("Circuit breaker thresholds must be positive")
        self.repository = repository
        self.clock = clock
        self.failure_threshold = failure_threshold
        self.success_threshold = success_threshold
        self.open_seconds = open_seconds
        self.maximum_half_open_probes = maximum_half_open_probes

    def allow(self, provider_id, capability):
        state = self.repository.get(provider_id, capability)
        now = self.clock()
        if state.status == ProviderHealthStatus.DISABLED:
            raise ProviderUnavailableError("Provider is disabled")
        if state.status == ProviderHealthStatus.OPEN:
            if state.open_until is None or state.open_until > now:
                raise ProviderUnavailableError("Provider circuit is open")
            version = state.version
            state.status = ProviderHealthStatus.HALF_OPEN
            state.half_open_probe_count = 0
            state.updated_at = now
            self.repository.save(state, expected_version=version)
        if state.status == ProviderHealthStatus.HALF_OPEN:
            if state.half_open_probe_count >= self.maximum_half_open_probes:
                raise ProviderUnavailableError("Provider half-open probe is occupied")
            version = state.version
            state.half_open_probe_count += 1
            state.current_in_flight += 1
            state.updated_at = now
            self.repository.save(state, expected_version=version)
        elif state.current_in_flight >= state.maximum_in_flight:
            raise ProviderUnavailableError("Provider is saturated")
        else:
            version = state.version
            state.current_in_flight += 1
            state.updated_at = now
            self.repository.save(state, expected_version=version)
        return state

    def success(self, provider_id, capability):
        state = self.repository.get(provider_id, capability)
        version, now = state.version, self.clock()
        state.current_in_flight = max(0, state.current_in_flight - 1)
        state.consecutive_successes += 1
        state.consecutive_failures = 0
        state.last_success_at = now
        if (
            state.status != ProviderHealthStatus.DISABLED
            and state.consecutive_successes >= self.success_threshold
        ):
            state.status = ProviderHealthStatus.HEALTHY
            state.open_until = None
            state.half_open_probe_count = 0
        state.updated_at = now
        return self.repository.save(state, expected_version=version)

    def failure(self, provider_id, capability, *, category, code):
        state = self.repository.get(provider_id, capability)
        version, now = state.version, self.clock()
        state.current_in_flight = max(0, state.current_in_flight - 1)
        state.consecutive_failures += 1
        state.consecutive_successes = 0
        state.last_failure_at = now
        state.last_failure_category = str(category)[:64]
        state.last_failure_code = str(code)[:128]
        if (
            state.status != ProviderHealthStatus.DISABLED
            and state.consecutive_failures >= self.failure_threshold
        ):
            state.status = ProviderHealthStatus.OPEN
            state.open_until = now + timedelta(seconds=self.open_seconds)
            state.half_open_probe_count = 0
        elif state.status != ProviderHealthStatus.DISABLED:
            state.status = ProviderHealthStatus.DEGRADED
        state.updated_at = now
        return self.repository.save(state, expected_version=version)
