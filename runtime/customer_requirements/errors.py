"""Customer requirements-refinement errors."""


class CustomerRequirementsError(Exception):
    """Base guided-requirements error."""


class RequirementsDraftNotFound(CustomerRequirementsError):
    """No draft exists for the customer-scoped product request."""


class RequirementsDraftConflict(CustomerRequirementsError):
    """A stale or conflicting revision was submitted."""


class RequirementsDraftCorrupt(CustomerRequirementsError):
    """Persisted requirements authority failed integrity validation."""


class RequirementsDraftLocked(RequirementsDraftConflict):
    """The customer approved this draft and further revisions are forbidden."""


class RequirementsApprovalError(CustomerRequirementsError):
    """Base customer requirements-approval error."""


class RequirementsApprovalNotFound(RequirementsApprovalError):
    """No approval receipt exists for this customer request."""


class RequirementsApprovalConflict(RequirementsDraftConflict, RequirementsApprovalError):
    """Approval authority conflicts with the current requirements draft."""


class RequirementsApprovalCorrupt(RequirementsDraftCorrupt, RequirementsApprovalError):
    """Persisted requirements-approval authority failed integrity validation."""
