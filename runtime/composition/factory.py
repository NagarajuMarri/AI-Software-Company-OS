"""Convenience factory for isolated ASCOS runtimes."""

from runtime.composition.container import (
    ASCOSRuntimeContainer,
    RuntimeContainerConfiguration,
)


def create_runtime_container(
    *,
    eventing_enabled: bool = True,
) -> ASCOSRuntimeContainer:
    """Create a new container with no global singleton state."""

    return ASCOSRuntimeContainer(
        RuntimeContainerConfiguration(eventing_enabled=eventing_enabled)
    )
