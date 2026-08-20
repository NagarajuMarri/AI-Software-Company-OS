"""Customer requirements-refinement errors."""


class CustomerRequirementsError(Exception):
    """Base guided-requirements error."""


class RequirementsDraftNotFound(CustomerRequirementsError):
    """No draft exists for the customer-scoped product request."""


class RequirementsDraftConflict(CustomerRequirementsError):
    """A stale or conflicting revision was submitted."""


class RequirementsDraftCorrupt(CustomerRequirementsError):
    """Persisted requirements authority failed integrity validation."""
