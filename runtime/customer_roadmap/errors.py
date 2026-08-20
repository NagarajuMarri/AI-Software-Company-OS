"""Customer-facing roadmap-draft errors."""


class CustomerRoadmapError(Exception):
    """Base customer roadmap error."""


class CustomerRoadmapNotFound(CustomerRoadmapError):
    """No roadmap draft exists for the customer request."""


class CustomerRoadmapConflict(CustomerRoadmapError):
    """Roadmap generation authority is missing, stale, or conflicting."""


class CustomerRoadmapCorrupt(CustomerRoadmapError):
    """Persisted customer roadmap authority failed integrity validation."""
