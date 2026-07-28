"""Convenience factory for isolated ASCOS runtimes."""

from runtime.composition.container import (
    ASCOSRuntimeContainer,
    RuntimeContainerConfiguration,
)


def create_runtime_container(
    *,
    eventing_enabled: bool = True,
    persistence_enabled: bool = False,
    persistence_provider: object | None = None,
    runtime_id: str = "default-runtime",
    automatic_checkpoint_policy: bool = False,
) -> ASCOSRuntimeContainer:
    """Create a new container with no global singleton state."""

    return ASCOSRuntimeContainer(
        RuntimeContainerConfiguration(
            eventing_enabled=eventing_enabled,
            persistence_enabled=persistence_enabled,
            persistence_provider=persistence_provider,
            runtime_id=runtime_id,
            automatic_checkpoint_policy=automatic_checkpoint_policy,
        )
    )
