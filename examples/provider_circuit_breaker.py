import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from runtime.providers.health import (
    CircuitBreaker, InMemoryProviderHealthRepository,
    ProviderHealthState, ProviderHealthStatus,
)


def main():
    now = [datetime.now(timezone.utc)]
    repository = InMemoryProviderHealthRepository()
    repository.add(ProviderHealthState(
        "demo", "coding", ProviderHealthStatus.HEALTHY, 0, 0, None, None,
        None, None, None, 0, 0, 2, now[0],
    ))
    circuit = CircuitBreaker(repository, clock=lambda: now[0], failure_threshold=2, open_seconds=5)
    transitions = ["HEALTHY"]
    for code in ("E1", "E2"):
        circuit.failure("demo", "coding", category="UNAVAILABLE", code=code)
        transitions.append(repository.get("demo", "coding").status.value)
    now[0] += timedelta(seconds=5)
    circuit.allow("demo", "coding")
    transitions.append(repository.get("demo", "coding").status.value)
    circuit.success("demo", "coding")
    transitions.append(repository.get("demo", "coding").status.value)
    print(" -> ".join(transitions))


if __name__ == "__main__": main()
