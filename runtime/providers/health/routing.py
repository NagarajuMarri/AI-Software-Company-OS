from dataclasses import dataclass

from runtime.providers.health.exceptions import ProviderUnavailableError
from runtime.providers.health.models import ProviderHealthStatus


@dataclass(frozen=True)
class ProviderRoute:
    provider_id: str
    capability: str
    priority: int = 100


class ProviderRouter:
    def __init__(self, health_repository, routes):
        self.health_repository = health_repository
        self.routes = tuple(routes)

    def select(self, capability, *, affinity_provider_id=None):
        eligible = []
        for route in self.routes:
            if route.capability != capability:
                continue
            state = self.health_repository.get(route.provider_id, capability)
            if state.status in {
                ProviderHealthStatus.OPEN, ProviderHealthStatus.DISABLED,
            } or state.current_in_flight >= state.maximum_in_flight:
                continue
            eligible.append(route)
        if affinity_provider_id is not None:
            for route in eligible:
                if route.provider_id == affinity_provider_id:
                    return route
        if not eligible:
            raise ProviderUnavailableError("No healthy provider supports capability")
        return min(eligible, key=lambda item: (item.priority, item.provider_id))
