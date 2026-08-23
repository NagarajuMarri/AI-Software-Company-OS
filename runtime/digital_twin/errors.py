"""Provider-neutral Digital Twin runtime failures."""


class DigitalTwinError(RuntimeError):
    """Base failure for the bounded Digital Twin runtime."""


class DigitalTwinPolicyError(DigitalTwinError):
    """The requested execution exceeds delegated authority or policy."""


class DigitalTwinToolPolicyError(DigitalTwinPolicyError):
    """A provider tool request exceeds its explicit allowlist or budget."""


class DigitalTwinRegistryError(DigitalTwinError):
    """A required provider or tool is missing or incompatible."""


class DigitalTwinExecutionError(DigitalTwinError):
    """A provider execution could not be accepted as trustworthy."""


class DigitalTwinStoreError(DigitalTwinError):
    """Persisted Digital Twin execution state is missing or corrupt."""


class DigitalTwinConflictError(DigitalTwinStoreError):
    """Write-once execution state conflicts with an existing record."""
