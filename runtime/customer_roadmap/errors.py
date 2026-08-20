"""Customer-facing roadmap-draft errors."""


class CustomerRoadmapError(Exception):
    """Base customer roadmap error."""


class CustomerRoadmapNotFound(CustomerRoadmapError):
    """No roadmap draft exists for the customer request."""


class CustomerRoadmapConflict(CustomerRoadmapError):
    """Roadmap generation authority is missing, stale, or conflicting."""


class CustomerRoadmapCorrupt(CustomerRoadmapError):
    """Persisted customer roadmap authority failed integrity validation."""


class CustomerRoadmapApprovalError(CustomerRoadmapError):
    """Base customer roadmap approval error."""


class CustomerRoadmapApprovalNotFound(CustomerRoadmapApprovalError):
    """No locked customer roadmap approval exists for the request."""


class CustomerRoadmapApprovalConflict(CustomerRoadmapApprovalError):
    """Roadmap approval authority is missing, stale, or conflicting."""


class CustomerRoadmapApprovalCorrupt(CustomerRoadmapApprovalError):
    """Persisted customer roadmap approval failed integrity validation."""
